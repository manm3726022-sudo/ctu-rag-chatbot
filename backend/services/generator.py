'''Sinh câu trả lời từ evidence (runbook §10.3).'''
from dataclasses import dataclass

from backend import prompts
from backend.schemas import EvidenceChunk
from backend.services import groq_client
from core import config
from core.tokens import count_tokens

TAGS = ('[ABSTAIN]', '[CLARIFY]')


@dataclass
class AnswerDraft:
    text: str
    abstain: bool = False
    clarify: bool = False
    finish_reason: str | None = None
    usage: dict | None = None
    model: str | None = None


def format_evidence(pack: list[EvidenceChunk]) -> str:
    '''Định dạng evidence đưa vào prompt. Đặt ở đây (TV4) vì đây là việc của prompt;
    runbook §9.1 để trong reranker.py, TV3 có thể import lại từ đây.'''
    blocks = []
    for e in pack:
        page = f'tr. {e.page_start}' if e.page_start else None
        loc = ', '.join(x for x in [e.doc_number or e.doc_title, e.section or e.article, page] if x)
        blocks.append(f'[{e.source_id}] ({loc})\n{e.text}')
    return '\n\n'.join(blocks)


def generate_answer(question: str, evidence_text: str) -> AnswerDraft:
    user = prompts.USER_TEMPLATE.format(evidence=evidence_text, question=question)
    est = count_tokens(prompts.SYSTEM_PROMPT) + count_tokens(user) + config.GROQ_MAX_OUTPUT_TOKENS
    resp = groq_client.chat(
        [{'role': 'system', 'content': prompts.SYSTEM_PROMPT}, {'role': 'user', 'content': user}], est
    )
    choice = resp.choices[0]
    text = (choice.message.content or '').strip()
    abstain, clarify = text.startswith(TAGS[0]), text.startswith(TAGS[1])
    for tag in TAGS:
        if text.startswith(tag):
            text = text[len(tag):].strip()
    usage = resp.usage.model_dump() if getattr(resp, 'usage', None) else None
    return AnswerDraft(text, abstain, clarify, choice.finish_reason, usage, getattr(resp, 'model', None))
