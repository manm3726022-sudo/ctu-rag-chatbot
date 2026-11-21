'''Chuẩn hóa câu hỏi và nhận diện phạm vi (Pipeline B5): số hiệu văn bản, "Điều N", "Phụ lục V.b",
học kỳ/năm học, khóa tuyển sinh, và câu hỏi về CHÍNH hiệu lực của văn bản.

Router chỉ đọc chữ trong câu hỏi, không gọi model và không đoán khi thiếu dữ kiện.
Nếu thiếu thông tin làm thay đổi đáp án thì để LLM hỏi lại ([CLARIFY]) theo prompt của TV4.'''
import re
import unicodedata
from dataclasses import dataclass

from core import corpus_catalog

_PREFIX = r'(qđ|qd|quyết định|tt|thông tư|hd|hđ|hướng dẫn)'
# "QĐ 3266", "QĐ3266", "Thông tư số 40", "TT40"
_MENTION_A = re.compile(rf'(?<!\w){_PREFIX}\s*(?:số\s*)?(\d{{1,5}})(?!\d)')
# "3266/QĐ-ĐHCT", "40/2026/TT-BGDĐT", "2427/HD-ĐHCT"
_MENTION_B = re.compile(rf'(?<!\d)(\d{{1,5}})\s*/\s*(?:\d{{4}}\s*/\s*)?{_PREFIX}(?!\w)')
# Số hiệu đứng riêng (từ 4 chữ số) khớp số hiệu trong kho: "QĐ học vụ 3266", "quy chế 4932"
_MENTION_BARE = re.compile(r'(?<![\d./,-])(\d{4,5})(?![\d/])')
_KIND = {
    'qđ': 'qd', 'qd': 'qd', 'quyết định': 'qd',
    'tt': 'tt', 'thông tư': 'tt',
    'hd': 'hd', 'hđ': 'hd', 'hướng dẫn': 'hd',
}
_ARTICLE = re.compile(r'(?<!\w)điều\s+(\d{1,3})(?!\d)')
_APPENDIX = re.compile(r'(?<!\w)phụ lục\s+([ivx]{1,4})(?:\.([a-e]))?(?!\w)')
_APPENDIX_DOTTED = re.compile(r'(?<![\w.])([ivx]{1,4})\.([a-e])(?![\w.])')
_SEMESTER = re.compile(r'(?<!\w)(?:học kỳ|học kì|hk)\s*(1|2|3|iii|ii|i|hè)(?!\w)')
_YEAR_RANGE = re.compile(r'(?<!\d)(20\d{2})\s*[-–—/]\s*(20\d{2})(?!\d)')
_YEAR_SINGLE = re.compile(r'năm học\s*(20\d{2})(?!\d)')
_COHORT = re.compile(r'(?<!\w)khóa\s*(\d{2})(?!\d)')
_SEM_VALUE = {'1': 1, 'i': 1, '2': 2, 'ii': 2, '3': 3, 'iii': 3, 'hè': 3}
# Câu hỏi về thời điểm/quan hệ hiệu lực của chính văn bản: KHÔNG lọc cứng theo học kỳ
# (ví dụ CTU-075 hỏi HK1 2024–2025 có thuộc kỳ áp dụng của QĐ 3266 không).
_VALIDITY = (
    'hiệu lực', 'áp dụng từ', 'bắt đầu áp dụng', 'kỳ áp dụng', 'kì áp dụng',
    'thay thế', 'thay cho', 'ban hành',
)


@dataclass
class Routed:
    question: str  # đã chuẩn hóa NFC + gộp khoảng trắng
    doc_number: str = None  # số hiệu văn bản được nêu đích danh đầu tiên (giữ tương thích mock)
    article: str = None  # "Điều 18" đầu tiên (giữ tương thích mock)
    term_key: int = None  # 20241 = HK1 năm học 2024–2025
    document_ids: tuple = ()  # văn bản được nêu đích danh VÀ có trong kho
    articles: tuple = ()  # ("Điều 14", ...)
    appendix_items: tuple = ()  # ("V.b", "I", ...)
    cohort: int = None  # khóa tuyển sinh nêu trong câu hỏi (chưa dùng để lọc vì payload chưa có)
    about_validity: bool = False


_KI = re.compile(r'(?<!\w)([Kk])ì(?!\w)')


def normalize(text: str) -> str:
    '''NFC, bỏ ký tự vô hình, gộp khoảng trắng, thống nhất "kì" -> "kỳ" (văn bản quy chế viết "kỳ"/"HK").'''
    text = unicodedata.normalize('NFC', text).translate({0xAD: None, 0x200B: None, 0xFEFF: None})
    return _KI.sub(lambda m: m[1] + 'ỳ', ' '.join(text.split()))


def _mentioned(low: str, catalog) -> list:
    found = []
    for kind_word, number in [(m[1], m[2]) for m in _MENTION_A.finditer(low)] + [
        (m[2], m[1]) for m in _MENTION_B.finditer(low)
    ]:
        kind = _KIND[kind_word]
        for doc in catalog:
            if doc.kind == kind and doc.number == number and doc not in found:
                found.append(doc)
    for m in _MENTION_BARE.finditer(low):
        for doc in catalog:
            if doc.number == m[1] and doc not in found:
                found.append(doc)
    return found


def _term(low: str):
    '''Chỉ trả học kỳ khi nêu đúng MỘT học kỳ và có năm học; không đoán khi mơ hồ.'''
    sems = {_SEM_VALUE[m[1]] for m in _SEMESTER.finditer(low)}
    if len(sems) != 1:
        return None
    year = None
    if m := _YEAR_RANGE.search(low):
        if int(m[2]) == int(m[1]) + 1:
            year = int(m[1])
    elif m := _YEAR_SINGLE.search(low):
        year = int(m[1])
    if year is None:
        return None
    return year * 10 + sems.pop()


def route(question: str, catalog=None) -> Routed:
    catalog = corpus_catalog.load_catalog() if catalog is None else catalog
    q = normalize(question)
    low = q.lower()
    docs = _mentioned(low, catalog)
    articles = tuple(dict.fromkeys(f'Điều {m[1]}' for m in _ARTICLE.finditer(low)))
    items = []
    for m in _APPENDIX.finditer(low):
        items.append(m[1].upper() + (f'.{m[2]}' if m[2] else ''))
    for m in _APPENDIX_DOTTED.finditer(low):
        items.append(f'{m[1].upper()}.{m[2]}')
    cohort = _COHORT.search(low)
    return Routed(
        question=q,
        doc_number=docs[0].document_number if docs else None,
        article=articles[0] if articles else None,
        term_key=_term(low),
        document_ids=tuple(d.document_id for d in docs),
        articles=articles,
        appendix_items=tuple(dict.fromkeys(items)),
        cohort=int(cohort[1]) if cohort else None,
        about_validity=any(k in low for k in _VALIDITY),
    )
