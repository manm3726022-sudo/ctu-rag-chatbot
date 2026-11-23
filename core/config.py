'''Đọc cấu hình từ .env. Mọi module import từ đây, không tự đọc os.environ rải rác (runbook §3.3).'''
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def _int(key, default):
    return int(os.getenv(key, default))


def _opt_float(key):
    v = os.getenv(key, '').strip()
    return float(v) if v else None


def _bool(key, default):
    return os.getenv(key, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


# --- Groq (chỉ backend đọc) ---
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')
GROQ_FALLBACK_MODEL = os.getenv('GROQ_FALLBACK_MODEL', 'openai/gpt-oss-20b')
GROQ_TIMEOUT_S = float(os.getenv('GROQ_TIMEOUT_S', '30'))
GROQ_MAX_OUTPUT_TOKENS = _int('GROQ_MAX_OUTPUT_TOKENS', 800)
GROQ_TPM_BUDGET = _int('GROQ_TPM_BUDGET', 6000)

# --- Qdrant / model local (TV3) ---
QDRANT_URL = os.getenv('QDRANT_URL', 'http://localhost:6333')
COLLECTION = os.getenv('QDRANT_COLLECTION', 'ctu_knowledge')
EMBED_BACKEND = os.getenv('EMBED_BACKEND', 'bge-m3').strip().lower()
RERANK_BACKEND = os.getenv('RERANK_BACKEND', 'bge').strip().lower()
EMBED_MODEL = os.getenv(
    'EMBED_MODEL', 'Alibaba-NLP/gte-multilingual-base' if EMBED_BACKEND == 'mgte' else 'BAAI/bge-m3',
)
RERANK_MODEL = os.getenv(
    'RERANK_MODEL', 'itdainb/PhoRanker' if RERANK_BACKEND == 'phoranker' else 'BAAI/bge-reranker-v2-m3',
)
EVIDENCE_TOKENIZER_MODEL = os.getenv('EVIDENCE_TOKENIZER_MODEL') or EMBED_MODEL
CHUNKING_MODE = os.getenv('CHUNKING_MODE', 'legacy').strip().lower()
USE_FP16 = os.getenv('USE_FP16', 'false').lower() == 'true'
RETRIEVE_PREFETCH = _int('RETRIEVE_PREFETCH', 20)
RETRIEVE_LIMIT = _int('RETRIEVE_LIMIT', 20)
EVIDENCE_MAX_CHUNKS = _int('EVIDENCE_MAX_CHUNKS', 6)
EVIDENCE_MAX_TOKENS = _int('EVIDENCE_MAX_TOKENS', 3000)
ABSTAIN_THRESHOLD = _opt_float('RERANK_ABSTAIN_THRESHOLD')  # None = chưa hiệu chỉnh

# --- Truy xuất: các tham số bổ sung của TV3 ---
# true: chỉ dùng đoạn review_status=checked làm bằng chứng (đúng hợp đồng TV1/TV2).
# false: gồm cả đoạn pending (để đo Recall trên bộ gold hoặc thử trước khi duyệt xong).
RETRIEVE_REQUIRE_CHECKED = _bool('RETRIEVE_REQUIRE_CHECKED', True)
RETRIEVE_MAX_PINNED = _int('RETRIEVE_MAX_PINNED', 8)  # số đoạn tối đa ghim theo "Điều N"/"Phụ lục"
EVIDENCE_DIVERSITY_RATIO = float(os.getenv('EVIDENCE_DIVERSITY_RATIO', '0.5'))
EMBED_QUERY_MAX_LENGTH = _int('EMBED_QUERY_MAX_LENGTH', 512)
RERANK_MAX_LENGTH = _int('RERANK_MAX_LENGTH', 1024)
RERANK_BATCH_SIZE = _int('RERANK_BATCH_SIZE', 8)
MANIFEST_PATH = Path(os.getenv('MANIFEST_PATH', '') or ROOT / 'docs/corpus/documents.json')
APPROVED_PATH = Path(os.getenv('APPROVED_CHUNKS_PATH', '') or ROOT / 'data/review/approved_chunks.csv')

# --- Chọn bộ truy xuất: 'mock' (dữ liệu giả, không cần Qdrant) hoặc 'real' (của TV3) ---
RETRIEVER = os.getenv('RETRIEVER', 'mock').strip().lower()
