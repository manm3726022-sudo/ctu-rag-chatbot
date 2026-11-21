'''Kiểm tra trích dẫn (runbook §11.1). Metadata nguồn lấy từ evidence, không lấy từ lời LLM.'''
import re

from backend.schemas import Citation, EvidenceChunk

RE_CITE = re.compile(r'\[S([0-9]+)\]')
# Mô hình hay gộp hoặc đổi dạng nhãn: [S1, S2], [S1 và S2], 【S1】, [S 1], (S1). Chuẩn hóa về [S1][S2]
# trước khi kiểm tra để câu trả lời đúng không bị coi là "không có trích dẫn".
RE_CITE_VARIANT = re.compile(
    r'[\[【（(]\s*(S\s*\d+(?:\s*(?:,|;|/|và|and)\s*(?:S\s*)?\d+)*)\s*[\]】）)]', re.IGNORECASE
)
RE_NUM = re.compile(r'[0-9]+(?:[.,][0-9]+)?')


def normalize_citations(text: str) -> str:
    return RE_CITE_VARIANT.sub(lambda m: ''.join(f'[S{n}]' for n in re.findall(r'\d+', m.group(1))), text)


def unsupported_numbers(answer: str, evidence: list[EvidenceChunk], question: str = '') -> list[str]:
    '''Số (từ 2 chữ số) có trong câu trả lời nhưng không có trong evidence hay câu hỏi.'''
    body = RE_CITE.sub('', normalize_citations(answer))
    known = set(RE_NUM.findall(' '.join(e.text for e in evidence) + ' ' + question))
    return sorted({n for n in RE_NUM.findall(body) if len(n) >= 2 and n not in known})


def validate(answer: str, evidence: list[EvidenceChunk], question: str = ''):
    '''Trả về (câu trả lời đã làm sạch, citations, danh sách cờ rủi ro).'''
    answer = normalize_citations(answer)
    by_id = {e.source_id: e for e in evidence}
    used, removed = [], []

    def keep(m):
        sid = 'S' + m.group(1)
        if sid not in by_id:
            removed.append(sid)
            return ''  # gỡ citation không tồn tại
        if sid not in used:
            used.append(sid)
        return m.group(0)

    clean = re.sub(r' {2,}', ' ', RE_CITE.sub(keep, answer)).strip()
    cites = []
    for s in used:
        e = by_id[s]
        doc = e.doc_title + (f' ({e.doc_number})' if e.doc_number else '')
        cites.append(Citation(source_id=s, document=doc, section=e.section or e.article,
                              page=e.page_start, url=e.source_url))
    flags = []
    if removed:
        flags.append('invalid_citation_removed')
    if not used:
        flags.append('no_citation')
    elif unsupported_numbers(clean, evidence, question):
        flags.append('unsupported_number')
    return clean, cites, flags
