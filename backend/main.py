'''FastAPI: POST /chat, GET /health (runbook §11.2).
Chạy: uvicorn backend.main:app --host 127.0.0.1 --port 8000'''
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.schemas import ChatRequest, ChatResponse
from backend.services import citation_validator, generator, groq_client, retrieval
from backend.services.conversation import (
    contextualize_question,
    is_confirmation_followup,
)
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
    t0 = time.perf_counter()
    confirmation_resolved = is_confirmation_followup(req.question, req.history)
    question = contextualize_question(req.question, req.history)
    try:
        res = retrieval.retrieve(question)
    except retrieval.RetrievalError as e:
        raise HTTPException(status_code=503, detail=f'Kho tài liệu tạm thời không truy cập được: {e}')
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
    timings_ms = dict(getattr(res, 'timings_ms', {}) or {})
    timings_ms.setdefault('retrieval_total_ms', retrieval_ms)
    ev = res.evidence
    if not ev:
        flag = 'no_valid_document_for_term' if res.routed.term_key else 'no_evidence'
        timings_ms['total_ms'] = round((time.perf_counter() - t0) * 1000, 1)
        _log(q=req.question, evidence=[], flags=[flag], routed=_routed_info(res),
             ms=int((time.perf_counter() - t0) * 1000), timings_ms=timings_ms)
        return ChatResponse(answer=ABSTAIN_MSG, abstain=True, risk_flag=flag)
    if (
        config.RERANK_ENABLED
        and config.ABSTAIN_THRESHOLD is not None
        and res.top_score < config.ABSTAIN_THRESHOLD
    ):
        timings_ms['total_ms'] = round((time.perf_counter() - t0) * 1000, 1)
        _log(q=req.question, evidence=[e.chunk_id for e in ev], scores=[round(e.score, 3) for e in ev],
             flags=['low_score'], routed=_routed_info(res), ms=int((time.perf_counter() - t0) * 1000),
             timings_ms=timings_ms)
        return ChatResponse(answer=ABSTAIN_MSG, abstain=True, risk_flag='low_score')
    answer_started = time.perf_counter()
    try:
        draft, text, cites, flags = _answer(question, ev)
    except groq_client.QuotaExhausted as e:
        raise HTTPException(status_code=503, detail=str(e), headers={'Retry-After': '60'})
    except groq_client.LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if draft.finish_reason == 'length':
        flags.append('truncated')
    if needs_verification(question):
        flags.append('needs_verification')
    if draft.clarify:
        flags = [flag for flag in flags if flag != 'no_citation']
        if confirmation_resolved:
            draft.clarify = False
            draft.abstain = True
            text = ABSTAIN_MSG
            cites = []
            flags.append('clarification_after_confirmation')
    timings_ms['generation_and_validation_ms'] = round(
        (time.perf_counter() - answer_started) * 1000, 1
    )
    if draft.clarify:
        out = ChatResponse(answer=text, need_clarification=True)
    elif draft.abstain or 'no_citation' in flags:
        out = ChatResponse(answer=text if (draft.abstain and text) else ABSTAIN_MSG, abstain=True)
    else:
        out = ChatResponse(answer=text, citations=cites)
    out.risk_flag = ','.join(flags) or None
    timings_ms['total_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    _log(q=req.question, evidence=[e.chunk_id for e in ev], scores=[round(e.score, 3) for e in ev],
         flags=flags, usage=draft.usage, model=draft.model, ms=int((time.perf_counter() - t0) * 1000),
         abstain=out.abstain, clarify=out.need_clarification, finish=draft.finish_reason,
         draft=(draft.text or '')[:600], answer=out.answer[:300], routed=_routed_info(res),
         rerank_enabled=config.RERANK_ENABLED, timings_ms=timings_ms)
    return out
