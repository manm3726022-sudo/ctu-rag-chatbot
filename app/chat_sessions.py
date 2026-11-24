"""Helpers for managing browser-persisted conversations."""
from uuid import uuid4

NEW_CONVERSATION_TITLE = 'Cuộc hội thoại mới'


def new_conversation() -> dict:
    return {
        'id': uuid4().hex,
        'title': NEW_CONVERSATION_TITLE,
        'messages': [],
    }


def create_conversation(
    conversations: list[dict],
) -> tuple[list[dict], str]:
    """Create a fresh conversation without discarding older conversations."""
    conversation = new_conversation()
    return [conversation, *conversations], conversation['id']


def delete_conversation(
    conversations: list[dict],
    deleted_id: str,
    active_id: str | None = None,
) -> tuple[list[dict], str]:
    """Delete only the selected conversation and return a valid active ID."""
    retained = [
        conversation
        for conversation in conversations
        if conversation['id'] != deleted_id
    ]
    if not retained:
        conversation = new_conversation()
        return [conversation], conversation['id']
    if active_id == deleted_id or not any(
        conversation['id'] == active_id for conversation in retained
    ):
        active_id = retained[0]['id']
    return retained, active_id


def rename_conversation(
    conversations: list[dict],
    conversation_id: str,
    title: str,
) -> None:
    """Rename one conversation without changing its messages or position."""
    title = title.strip()
    if not title:
        raise ValueError('Tên cuộc hội thoại không được để trống')
    for conversation in conversations:
        if conversation['id'] == conversation_id:
            conversation['title'] = title
            return
    raise ValueError('Không tìm thấy cuộc hội thoại cần đổi tên')


def validate_conversations(value) -> list[dict]:
    """Validate persisted browser data before using it as chat history."""
    if not isinstance(value, list):
        raise TypeError('Dữ liệu cuộc hội thoại phải là một danh sách')

    conversations = []
    seen_ids = set()
    for conversation in value:
        if not isinstance(conversation, dict):
            raise TypeError('Dữ liệu một cuộc hội thoại không hợp lệ')
        conversation_id = conversation.get('id')
        title = conversation.get('title')
        messages = conversation.get('messages')
        if (
            not isinstance(conversation_id, str)
            or not conversation_id
            or conversation_id in seen_ids
            or not isinstance(title, str)
            or not isinstance(messages, list)
        ):
            raise ValueError('Thông tin cuộc hội thoại không hợp lệ')
        seen_ids.add(conversation_id)
        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get('role') not in {'user', 'assistant'}
                or not isinstance(message.get('content'), str)
            ):
                raise ValueError('Thông tin tin nhắn trong lịch sử không hợp lệ')
        conversations.append(conversation)
    return conversations


def conversation_title(question: str, max_length: int = 48) -> str:
    title = ' '.join(question.split())
    if len(title) > max_length:
        return f'{title[:max_length - 3].rstrip()}...'
    return title or NEW_CONVERSATION_TITLE
