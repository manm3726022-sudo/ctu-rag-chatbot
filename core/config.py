'''Đọc cấu hình từ .env. Mọi module import từ đây, không tự đọc os.environ rải rác (runbook §3.3).'''
import os

from dotenv import load_dotenv

load_dotenv()


def _int(key, default):
    return int(os.getenv(key, default))


def _opt_float(key):
    v = os.getenv(key, '').strip()
    return float(v) if v else None


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
EMBED_MODEL = os.getenv('EMBED_MODEL', 'BAAI/bge-m3')
RERANK_MODEL = os.getenv('RERANK_MODEL', 'BAAI/bge-reranker-v2-m3')
USE_FP16 = os.getenv('USE_FP16', 'false').lower() == 'true'
RETRIEVE_PREFETCH = _int('RETRIEVE_PREFETCH', 20)
RETRIEVE_LIMIT = _int('RETRIEVE_LIMIT', 20)
EVIDENCE_MAX_CHUNKS = _int('EVIDENCE_MAX_CHUNKS', 6)
EVIDENCE_MAX_TOKENS = _int('EVIDENCE_MAX_TOKENS', 3000)
ABSTAIN_THRESHOLD = _opt_float('RERANK_ABSTAIN_THRESHOLD')  # None = chưa hiệu chỉnh

# --- Chọn bộ truy xuất: 'mock' (dữ liệu giả, không cần Qdrant) hoặc 'real' (của TV3) ---
RETRIEVER = os.getenv('RETRIEVER', 'mock').strip().lower()
