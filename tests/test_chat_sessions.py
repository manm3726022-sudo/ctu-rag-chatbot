from app.chat_sessions import (
    MAX_ARCHIVED_CONVERSATIONS,
    NEW_CONVERSATION_TITLE,
    conversation_title,
    create_conversation,
)


def test_create_conversation_preserves_messages_and_limits_archived_sessions():
    existing = [
        {'id': str(index), 'title': f'Chat {index}', 'messages': [{'content': str(index)}]}
        for index in range(MAX_ARCHIVED_CONVERSATIONS + 2)
    ]

    conversations, active_id = create_conversation(existing)

    assert len(conversations) == MAX_ARCHIVED_CONVERSATIONS + 1
    assert conversations[0]['id'] == active_id
    assert conversations[0]['messages'] == []
    assert [conversation['id'] for conversation in conversations[1:]] == [
        str(index) for index in range(MAX_ARCHIVED_CONVERSATIONS)
    ]
    assert conversations[1]['messages'] == [{'content': '0'}]


def test_create_conversation_keeps_active_chat_even_if_it_is_oldest():
    existing = [
        {'id': str(index), 'title': f'Chat {index}', 'messages': [{'content': str(index)}]}
        for index in range(MAX_ARCHIVED_CONVERSATIONS + 1)
    ]

    conversations, _ = create_conversation(existing, active_id=str(MAX_ARCHIVED_CONVERSATIONS))

    assert str(MAX_ARCHIVED_CONVERSATIONS) == conversations[1]['id']
    assert len(conversations) == MAX_ARCHIVED_CONVERSATIONS + 1


def test_conversation_title_uses_first_question_and_truncates_long_text():
    assert conversation_title('   Câu hỏi   đầu tiên  ') == 'Câu hỏi đầu tiên'
    assert conversation_title('a' * 60) == f'{"a" * 45}...'
    assert conversation_title('  ') == NEW_CONVERSATION_TITLE
