from types import SimpleNamespace

from core import embedding
from ingestion import index
from tests.fakes import FakeModel


def test_sparse_sap_xep_tang_dan_va_doi_khoa_sang_int():
    assert embedding.sparse_from_lexical({'30': 0.5, '4': 0.25, '100': 0.1}) == ([4, 30, 100], [0.25, 0.5, 0.1])
    assert embedding.sparse_from_lexical({}) == ([], [])


def test_encode_tra_dense_va_sparse():
    out = embedding.encode(['Mỗi học kỳ đăng ký bao nhiêu tín chỉ'], model=FakeModel())
    assert len(out) == 1 and len(out[0].dense) == 32 and out[0].indices == sorted(out[0].indices)
    assert len(out[0].indices) == len(out[0].values) > 0
    assert embedding.encode([], model=FakeModel()) == []


def test_encode_truyen_dung_tham_so():
    seen = {}

    class Spy:
        def encode(self, texts, **kwargs):
            seen.update(kwargs)
            return {'dense_vecs': [[0.0] * 4], 'lexical_weights': [{'7': 1.0}]}

    embedding.encode(['x'], model=Spy(), max_length=123)
    assert seen['max_length'] == 123 and seen['return_dense'] and seen['return_sparse'] and not seen['return_colbert_vecs']


def test_sparse_phia_truy_van_giong_het_phia_ingestion():
    '''Nếu hai phía lệch nhau thì hybrid search sẽ im lặng trả kết quả sai: test này giữ chúng đồng bộ.'''

    class CorpusModel(FakeModel):
        def encode_corpus(self, texts, **kwargs):
            return self.encode(texts, **kwargs)

    chunk = SimpleNamespace(
        chunk_id='11111111-1111-5111-8111-111111111111',
        section='Quy định > Điều 14', content='Tối đa 20 tín chỉ mỗi học kỳ',
        model_dump=lambda mode='json': {'chunk_id': 'c1', 'content': 'Tối đa 20 tín chỉ mỗi học kỳ',
                                        'section': 'Quy định > Điều 14'},
    )
    doc = SimpleNamespace(title='Quy định học vụ', model_dump=lambda mode='json', include=None: {'title': 'Quy định học vụ'})
    source = SimpleNamespace(file_name='f.pdf', source_kind='pdf_text')
    (point,) = index.encode(CorpusModel(), doc, source, [chunk])
    text = f'{doc.title}\n{chunk.section}\n{chunk.content}'
    q = embedding.encode([text], model=FakeModel())[0]
    assert point.vector['sparse'].indices == q.indices and point.vector['sparse'].values == q.values
    assert point.vector['dense'] == q.dense
