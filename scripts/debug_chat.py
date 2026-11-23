'''Chẩn đoán MỘT câu hỏi qua đúng đường đi của API, in từng bước để biết chatbot từ chối ở khâu nào.

  python -m scripts.debug_chat "Mỗi học kỳ được đăng ký tối đa bao nhiêu tín chỉ?"
  python -m scripts.debug_chat --pending "câu hỏi"     # tính cả đoạn pending (mặc định theo RETRIEVE_REQUIRE_CHECKED)
  python -m scripts.debug_chat --no-llm "câu hỏi"      # chỉ xem truy xuất, không tốn lượt gọi Groq

Các khâu: (1) router đọc câu hỏi; (2) bằng chứng được chọn, kèm điểm và số token; (3) lời mô hình thô;
(4) kết quả kiểm tra trích dẫn; (5) kết luận: API sẽ trả gì và vì sao. Tốn đúng 1 lượt Groq (trừ --no-llm).'''
import argparse

from core import config

ABSTAIN_MSG = 'Kho tài liệu hiện tại chưa đủ căn cứ để xác nhận nội dung này.'


def diagnose(question, require_checked=None, call_llm=True, search=None, generate=None, tokens=None):
    '''Trả về dict kết quả từng khâu. search/generate/tokens có thể thay bằng bản giả khi test.'''
    from backend.services import citation_validator, generator, retriever

    search = search or retriever.search
    generate = generate or generator.generate_answer
    tokens = tokens or __import__('core.tokens', fromlist=['count_tokens']).count_tokens
    filters = None if require_checked is None else {'require_checked': require_checked}
    res = search(question, filters)
    r = res.routed
    report = {
        'routed': {
            'question': r.question, 'docs': list(r.document_ids), 'articles': list(r.articles),
            'appendix': list(r.appendix_items), 'term_key': r.term_key, 'about_validity': r.about_validity,
        },
        'reason': res.reason,
        'n_candidates': len(res.fused),
        'timings_ms': getattr(res, 'timings_ms', {}),
        'evidence': [],
    }
    evidence = retriever.to_evidence(res.selected)
    for ev, cand in zip(evidence, res.selected, strict=True):
        report['evidence'].append({
            'source_id': ev.source_id, 'score': round(cand.final_score, 3), 'document': ev.doc_number,
            'section': ev.section, 'pages': f'{ev.page_start}-{ev.page_end}',
            'status': cand.payload.get('review_status'), 'tokens': tokens(ev.text), 'text': ev.text,
        })
    if not evidence:
        report['verdict'] = ('KHÔNG có bằng chứng: API trả ngay câu từ chối và KHÔNG gọi Groq '
                             f'(lý do: {res.reason or "không tìm thấy đoạn nào"}).')
        return report
    if not call_llm:
        report['verdict'] = 'Đã dừng trước khi gọi Groq (--no-llm).'
        return report

    ev_text = generator.format_evidence(evidence)
    draft = generate(question, ev_text)
    clean, cites, flags = citation_validator.validate(draft.text, evidence, question)
    report['draft'] = {
        'raw': draft.text, 'abstain_tag': draft.abstain, 'clarify_tag': draft.clarify,
        'finish_reason': draft.finish_reason, 'usage': draft.usage,
    }
    report['validation'] = {'clean': clean, 'cited': [c.source_id for c in cites], 'flags': flags}
    if draft.clarify:
        report['verdict'] = 'Mô hình HỎI LẠI (CLARIFY): giao diện hiện câu hỏi làm rõ.'
    elif draft.abstain:
        why = 'mô hình tự từ chối ([ABSTAIN]) vì cho rằng evidence không đủ'
        if not draft.text.strip():
            why += ', và KHÔNG kèm lời giải thích nên giao diện hiện câu từ chối mặc định'
        report['verdict'] = f'TỪ CHỐI: {why}.'
    elif 'no_citation' in flags:
        report['verdict'] = ('TỪ CHỐI: mô hình có trả lời nhưng KHÔNG có nhãn [S#] hợp lệ. API sẽ gọi lại một lần; '
                             'nếu vẫn thiếu, giao diện hiện câu từ chối mặc định dù nội dung có thể đúng.')
    else:
        report['verdict'] = 'TRẢ LỜI CÓ TRÍCH DẪN: ' + ', '.join(c.source_id for c in cites)
    return report


def print_report(rep: dict) -> None:
    r = rep['routed']
    print('\n== 1. Router')
    print(f"  câu hỏi chuẩn hóa: {r['question']}")
    print(f"  văn bản={r['docs']} điều={r['articles']} phụ lục={r['appendix']} kỳ={r['term_key']} hiệu lực={r['about_validity']}")
    print(f"\n== 2. Bằng chứng (ứng viên sau RRF: {rep['n_candidates']}, lý do rỗng: {rep['reason']})")
    if rep['timings_ms']:
        print(f"  thời gian các bước (ms): {rep['timings_ms']}")
    total = 0
    for e in rep['evidence']:
        total += e['tokens']
        print(f"  {e['source_id']} điểm={e['score']} {e['document']} | {e['section']} | tr.{e['pages']} | {e['status']} | {e['tokens']} token")
        print(f"     {e['text'][:140]!r}")
    if rep['evidence']:
        print(f"  tổng token bằng chứng: {total} (giới hạn EVIDENCE_MAX_TOKENS={config.EVIDENCE_MAX_TOKENS})")
    if 'draft' in rep:
        d = rep['draft']
        print('\n== 3. Lời mô hình thô (chưa kiểm tra)')
        print(f"  {d['raw']!r}")
        print(f"  thẻ ABSTAIN={d['abstain_tag']} CLARIFY={d['clarify_tag']} finish_reason={d['finish_reason']} usage={d['usage']}")
        v = rep['validation']
        print('\n== 4. Kiểm tra trích dẫn')
        print(f"  nhãn hợp lệ được dùng: {v['cited']} | cờ: {v['flags']}")
    print('\n== 5. KẾT LUẬN')
    print(' ', rep['verdict'])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('question', nargs='+')
    parser.add_argument('--pending', action='store_true', help='tính cả đoạn pending')
    parser.add_argument('--checked', action='store_true', help='chỉ đoạn checked')
    parser.add_argument('--no-llm', action='store_true')
    args = parser.parse_args()
    mode = False if args.pending else (True if args.checked else None)
    print(f'RETRIEVER={config.RETRIEVER} RETRIEVE_REQUIRE_CHECKED={config.RETRIEVE_REQUIRE_CHECKED} (lệnh này: {mode})')
    print_report(diagnose(' '.join(args.question), mode, call_llm=not args.no_llm))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
