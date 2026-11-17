'''FastAPI: POST /chat, GET /health (runbook §11.2).
Chạy: uvicorn backend.main:app --host 127.0.0.1 --port 8000'''
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.schemas import ChatRequest, ChatResponse
from backend.services import citation_validator, generator, groq_client, retrieval
from core import config

ABSTAIN_MSG = 'Kho tài liệu hiện tại chưa đủ căn cứ để xác nhận nội dung này.'
# Chủ đề cần đơn vị có thẩm quyền xác nhận (Pipeline mục 4.1: "Kém" ở QĐ 3266 và "Yếu" ở QĐ 4932).
# TV1 bổ sung khi phát hiện thêm.
VERIFY_RULES = [(('rèn luyện',), ('kém', 'yếu'))]


@asynccontextmanager
async def lifespan(app):
    retrieval.warmup()
    yield


app = FastAPI(title='CTU RAG Chatbot', lifespan=lifespan)


@app.get('/health')
def health():
    return {**retrieval.health(), 'groq_key_set': bool(config.GROQ_API_KEY)}


def needs_verification(q: str) -> bool:
    q = q.lower()
    return any(all(a in q for a in must) and any(b in q for b in any_of) for must, any_of in VERIFY_RULES)


def _answer(question, evidence):
    '''Sinh và kiểm tra trích dẫn; sinh lại đúng một lần nếu không có citation hợp lệ (D3).'''
    ev_text = generator.format_evidence(evidence)
    draft = generator.generate_answer(question, ev_text)
    text, cites, flags = citation_validator.validate(draft.text, evidence, question)
    if 'no_citation' in flags and not (draft.abstain or draft.clarify):
        try:
            draft = generator.generate_answer(question, ev_text)
            text, cites, flags = citation_validator.validate(draft.text, evidence, question)
        except (groq_client.QuotaExhausted, groq_client.LLMUnavailable):
            pass
    return draft, text, cites, flags


def _log(**kw):
    try:
        Path('logs').mkdir(exist_ok=True)
        with open('logs/chat.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(kw, ensure_ascii=False) + '\n')
    except OSError:
        pass


@app.post('/chat', response_model=ChatResponse)
def chat(req: ChatRequest):
    t0 = time.time()
    res = retrieval.retrieve(req.question)
    ev = res.evidence
    if not ev:
        flag = 'no_valid_document_for_term' if res.routed.term_key else 'no_evidence'
        return ChatResponse(answer=ABSTAIN_MSG, abstain=True, risk_flag=flag)
    if config.ABSTAIN_THRESHOLD is not None and res.top_score < config.ABSTAIN_THRESHOLD:
        return ChatResponse(answer=ABSTAIN_MSG, abstain=True, risk_flag='low_score')
    try:
        draft, text, cites, flags = _answer(req.question, ev)
    except groq_client.QuotaExhausted as e:
        raise HTTPException(status_code=503, detail=str(e), headers={'Retry-After': '60'})
    except groq_client.LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if draft.finish_reason == 'length':
        flags.append('truncated')
    if needs_verification(req.question):
        flags.append('needs_verification')
    if draft.clarify:
        out = ChatResponse(answer=text, need_clarification=True)
    elif draft.abstain or 'no_citation' in flags:
        out = ChatResponse(answer=text if (draft.abstain and text) else ABSTAIN_MSG, abstain=True)
    else:
        out = ChatResponse(answer=text, citations=cites)
    out.risk_flag = ','.join(flags) or None
    _log(q=req.question, evidence=[e.chunk_id for e in ev], scores=[round(e.score, 3) for e in ev],
         flags=flags, usage=draft.usage, model=draft.model, ms=int((time.time() - t0) * 1000))
    return out
