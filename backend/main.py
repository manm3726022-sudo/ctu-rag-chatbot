'''FastAPI: POST /chat, GET /health (runbook §11.2).
Chạy: uvicorn backend.main:app --host 127.0.0.1 --port 8000'''
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.schemas import ChatRequest, ChatResponse
from backend.services import citation_validator, generator, groq_client, retrieval
from backend.services.verify_rules import VERIFY_RULES, needs_verification  # noqa: F401
from core import config

ABSTAIN_MSG = 'Kho tài liệu hiện tại chưa đủ căn cứ để xác nhận nội dung này.'
# Lần sinh lại (D3) kèm lời nhắc: sinh lại y nguyên thì mô hình thường lặp lại đúng lỗi thiếu nhãn nguồn.
RETRY_NOTE = (
    'LƯU Ý: câu trả lời trước thiếu nhãn nguồn hợp lệ. Hãy trả lời lại, mỗi mệnh đề gắn đúng nhãn [S#] có trong '
    'EVIDENCE, mỗi nhãn trong một cặp ngoặc vuông riêng (ví dụ [S1][S2]). Nếu evidence không đủ thì dòng đầu là '
    '[ABSTAIN] kèm một câu giải thích bằng tiếng Việt.'
)


@asynccontextmanager
async def lifespan(app):
    retrieval.warmup()
    yield


app = FastAPI(title='CTU RAG Chatbot', lifespan=lifespan)


@app.get('/health')
def health():
    return {**retrieval.health(), 'groq_key_set': bool(config.GROQ_API_KEY)}


def _answer(question, evidence):
    '''Sinh và kiểm tra trích dẫn; sinh lại đúng một lần nếu không có citation hợp lệ (D3).'''
    ev_text = generator.format_evidence(evidence)
    draft = generator.generate_answer(question, ev_text)
    text, cites, flags = citation_validator.validate(draft.text, evidence, question)
    if 'no_citation' in flags and not (draft.abstain or draft.clarify):
        try:
            draft = generator.generate_answer(question, ev_text + '\n\n' + RETRY_NOTE)
            text, cites, flags = citation_validator.validate(draft.text, evidence, question)
        except (groq_client.QuotaExhausted, groq_client.LLMUnavailable):
            pass
    return draft, text, cites, flags


def _routed_info(res) -> dict:
    r = getattr(res, 'routed', None)
    return {
        'docs': list(getattr(r, 'document_ids', ()) or ()),
        'articles': list(getattr(r, 'articles', ()) or ()),
        'term_key': getattr(r, 'term_key', None),
        'about_validity': getattr(r, 'about_validity', None),
    }


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
    try:
        res = retrieval.retrieve(req.question)
    except retrieval.RetrievalError as e:
        raise HTTPException(status_code=503, detail=f'Kho tài liệu tạm thời không truy cập được: {e}')
    ev = res.evidence
    if not ev:
        flag = 'no_valid_document_for_term' if res.routed.term_key else 'no_evidence'
        _log(q=req.question, evidence=[], flags=[flag], routed=_routed_info(res), ms=int((time.time() - t0) * 1000))
        return ChatResponse(answer=ABSTAIN_MSG, abstain=True, risk_flag=flag)
    if config.ABSTAIN_THRESHOLD is not None and res.top_score < config.ABSTAIN_THRESHOLD:
        _log(q=req.question, evidence=[e.chunk_id for e in ev], scores=[round(e.score, 3) for e in ev],
             flags=['low_score'], routed=_routed_info(res), ms=int((time.time() - t0) * 1000))
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
         flags=flags, usage=draft.usage, model=draft.model, ms=int((time.time() - t0) * 1000),
         abstain=out.abstain, clarify=out.need_clarification, finish=draft.finish_reason,
         draft=(draft.text or '')[:600], answer=out.answer[:300], routed=_routed_info(res))
    return out
