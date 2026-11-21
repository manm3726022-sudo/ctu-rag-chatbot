'''Đánh giá truy xuất trên bộ gold (Pipeline B10, Sổ tay T17). Không gọi Groq.

  python -m eval.run_retrieval_eval                       # validation, gồm cả đoạn pending
  python -m eval.run_retrieval_eval --split test          # CHỈ chạy lúc nghiệm thu cuối
  python -m eval.run_retrieval_eval --checked-only        # đúng như chế độ demo (chỉ đoạn đã duyệt)

Báo cáo ba giai đoạn: "fused" (sau RRF), "ranked" (sau reranker), "evidence" (gói bằng chứng thật gửi cho
LLM). Mục tiêu nội bộ: Recall@5 (hit) >= 90% ở giai đoạn ranked/evidence.'''
import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from core import config
from eval.metrics import aggregate, case_metrics, split_of

ROOT = config.ROOT
STAGES = ('fused', 'ranked', 'evidence')


def load_gold(path: Path) -> list:
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def select_cases(gold: list, split: str) -> list:
    '''Chỉ các câu action=answer có nguồn mới đo được Recall; split: validation | test | all.'''
    cases = [g for g in gold if g['action'] == 'answer' and g['sources']]
    return cases if split == 'all' else [g for g in cases if split_of(g['case_id']) == split]


def _payloads(items) -> list:
    return [c.payload for c in items]


def evaluate(cases: list, search, k: int = 5, filters: dict = None) -> dict:
    '''search(question, filters) -> SearchResult (backend.services.retriever.search). Tách hàm này khỏi
    I/O để test được bằng search giả.'''
    per_case, per_stage = [], {s: [] for s in STAGES}
    by_category = {s: defaultdict(list) for s in STAGES}
    for case in cases:
        res = search(case['question'], filters)
        stage_items = {
            'fused': _payloads(res.fused),
            'ranked': _payloads(res.ranked),
            'evidence': _payloads(res.selected),
        }
        row = {'case_id': case['case_id'], 'category': case['category'], 'question': case['question']}
        for stage, chunks in stage_items.items():
            m = case_metrics(chunks, case['sources'], k)
            per_stage[stage].append(m)
            by_category[stage][case['category']].append(m)
            row[f'{stage}_hit'] = m['hit']
            row[f'{stage}_full'] = m['full']
        row['reason'] = res.reason or ''
        row['top_score'] = round(res.ranked[0].final_score, 4) if res.ranked else 0.0
        row['top'] = ' | '.join(
            f"{c.get('document_id')}:{c.get('section')}:{c.get('page_start')}" for c in stage_items['ranked'][:3]
        )
        per_case.append(row)
    return {
        'k': k,
        'overall': {s: aggregate(per_stage[s]) for s in STAGES},
        'by_category': {s: {cat: aggregate(v) for cat, v in by_category[s].items()} for s in STAGES},
        'cases': per_case,
        'top_score_found': score_summary(per_case),
    }


def score_summary(cases: list) -> dict:
    '''Điểm reranker của đoạn đầu ở các câu ĐÃ tìm đúng nguồn: dùng để chọn RERANK_ABSTAIN_THRESHOLD.
    Ngưỡng từ chối (nếu dùng) phải thấp hơn mức thấp nhất này, nếu không sẽ từ chối nhầm câu trả lời được.'''
    scores = sorted(c['top_score'] for c in cases if c['evidence_hit'] >= 1.0 and not c['reason'])
    if not scores:
        return {'n': 0}
    pick = lambda q: scores[min(len(scores) - 1, int(q * len(scores)))]  # noqa: E731
    return {'n': len(scores), 'min': scores[0], 'p10': pick(0.10), 'median': pick(0.5)}


def print_report(report: dict, label: str) -> None:
    k = report['k']
    print(f'\n=== Truy xuất trên {label} (k={k}) ===')
    print(f"{'giai đoạn':<10} {'n':>3} {'Recall@k':>9} {'đủ nguồn':>9} {'Prec@k':>7} {'MRR':>6}")
    for stage in STAGES:
        a = report['overall'][stage]
        print(f"{stage:<10} {a['n']:>3} {a['hit']:>9.1%} {a['full']:>9.1%} {a['precision']:>7.1%} {a['mrr']:>6.3f}")
    print('\nTheo nhóm câu hỏi (Recall@k giai đoạn evidence):')
    for cat, a in sorted(report['by_category']['evidence'].items()):
        print(f"  {cat:<15} n={a['n']:>3}  Recall@k={a['hit']:.1%}  đủ nguồn={a['full']:.1%}")
    ss = report.get('top_score_found') or score_summary(report['cases'])
    if ss['n']:
        print(f"\nĐiểm reranker của đoạn đầu ở {ss['n']} câu tìm đúng nguồn: thấp nhất={ss['min']:.3f}, "
              f"phân vị 10%={ss['p10']:.3f}, trung vị={ss['median']:.3f}")
        print('  -> nếu đặt RERANK_ABSTAIN_THRESHOLD thì phải thấp hơn nhiều so với mức thấp nhất này.')
    misses = [c for c in report['cases'] if c['evidence_hit'] < 1.0]
    print(f'\nCâu KHÔNG tìm thấy nguồn trong evidence: {len(misses)}')
    for c in misses[:15]:
        print(f"  {c['case_id']} [{c['category']}] {c['question'][:70]} -> {c['reason'] or c['top']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--gold', type=Path, default=ROOT / 'eval/gold_corpus.jsonl')
    parser.add_argument('--split', choices=['validation', 'test', 'all'], default='validation')
    parser.add_argument('--k', type=int, default=5)
    parser.add_argument('--checked-only', action='store_true', help='chỉ dùng đoạn review_status=checked')
    parser.add_argument('--out', type=Path, default=ROOT / 'eval/results')
    args = parser.parse_args()

    from backend.services import retriever  # import muộn: tải model nặng, chỉ khi thật sự chạy

    cases = select_cases(load_gold(args.gold), args.split)
    filters = {'require_checked': args.checked_only}
    started = time.time()
    report = evaluate(cases, retriever.search, args.k, filters)
    report['seconds'] = round(time.time() - started, 1)
    report['require_checked'] = args.checked_only
    print_report(report, f"{len(cases)} câu {args.split} ({'checked' if args.checked_only else 'gồm pending'})")

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    (args.out / f'retrieval-{args.split}-{stamp}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    with (args.out / f'retrieval-{args.split}-{stamp}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(report['cases'][0].keys()) if report['cases'] else ['case_id'])
        writer.writeheader()
        writer.writerows(report['cases'])
    print(f"\nĐã ghi báo cáo vào {args.out}/ (thư mục này nằm trong .gitignore)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
