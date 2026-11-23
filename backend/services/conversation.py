"""Resolve short follow-ups after the assistant explicitly asked for clarification."""

import re
import unicodedata

from backend.schemas import ChatTurn

CONFIRMATION_MARKERS = (
    'vui lòng xác nhận',
    'hãy xác nhận',
    'bạn muốn biết',
    'ý bạn là',
    'đúng không',
    'phải không',
)
AFFIRMATIVE = re.compile(
    r'^(?:dạ\s*)?(?:đúng(?: vậy| rồi)?|vâng|phải|chính xác)(?:\s+ạ)?[.!?]*$'
)


def _pending_history(history: list[ChatTurn]) -> list[ChatTurn]:
    if (
        not history
        or history[-1].role != 'assistant'
        or not history[-1].need_clarification
    ):
        return []

    last_completed_turn = max(
        (
            index
            for index, turn in enumerate(history)
            if turn.role == 'assistant' and not turn.need_clarification
        ),
        default=-1,
    )
    pending = history[last_completed_turn + 1 :]
    return pending if any(turn.role == 'user' for turn in pending) else []


def is_confirmation_followup(question: str, history: list[ChatTurn]) -> bool:
    pending = _pending_history(history)
    assistant_questions = [turn.content.lower() for turn in pending if turn.role == 'assistant']
    if not assistant_questions or not any(
        marker in assistant_questions[-1] for marker in CONFIRMATION_MARKERS
    ):
        return False

    answer = unicodedata.normalize('NFC', question).lower().strip()
    return bool(AFFIRMATIVE.fullmatch(answer))


def contextualize_question(question: str, history: list[ChatTurn]) -> str:
    pending = _pending_history(history)
    if not pending:
        return question

    if is_confirmation_followup(question, history):
        user_messages = [turn.content for turn in pending if turn.role == 'user']
        original = user_messages[0]
        details = '\n'.join(f'Thông tin bổ sung: {text}' for text in user_messages[1:])
        if details:
            details = f'\n{details}'
        return (
            f'Câu hỏi gốc của người dùng: {original}{details}\n'
            'Người dùng xác nhận cách diễn giải ở lượt trước là đúng. '
            'Hãy trả lời câu hỏi gốc từ EVIDENCE; không hỏi xác nhận lại. '
            'Nếu EVIDENCE không đủ thì từ chối, không yêu cầu người dùng cung cấp tên văn bản.'
        )

    labels = {'user': 'Người dùng', 'assistant': 'Trợ lý đã hỏi làm rõ'}
    context = '\n'.join(f'{labels[turn.role]}: {turn.content}' for turn in pending)
    return (
        'Ngữ cảnh làm rõ của câu hỏi trước (chỉ dùng để hiểu hội thoại, '
        'không phải bằng chứng):\n'
        f'{context}\n'
        f'Thông tin người dùng vừa bổ sung: {question}'
    )
