"""Helpers for keeping a small set of conversations in Streamlit session state."""

from uuid import uuid4

MAX_ARCHIVED_CONVERSATIONS = 5
NEW_CONVERSATION_TITLE = 'Cuộc hội thoại mới'


def new_conversation() -> dict:
    return {
        'id': uuid4().hex,
        'title': NEW_CONVERSATION_TITLE,
        'messages': [],
    }


def create_conversation(
    conversations: list[dict],
    active_id: str | None = None,
    max_archived: int = MAX_ARCHIVED_CONVERSATIONS,
) -> tuple[list[dict], str]:
    """Create a fresh active conversation and retain up to max_archived older ones."""
    conversation = new_conversation()
    previous = list(conversations)
    if active_id is not None:
        previous.sort(key=lambda item: item['id'] != active_id)
    retained = [conversation, *previous][: max_archived + 1]
    return retained, conversation['id']


def conversation_title(question: str, max_length: int = 48) -> str:
    title = ' '.join(question.split())
    if len(title) > max_length:
        return f'{title[:max_length - 3].rstrip()}...'
    return title or NEW_CONVERSATION_TITLE
