from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from app import api_client
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


@pytest.mark.parametrize(('headers', 'message'), [
    ({'Retry-After': '43'}, 'Đã chạm hạn mức token. Vui lòng thử lại sau 43 giây.'),
    ({}, 'Dịch vụ trả lời tạm thời không khả dụng. Vui lòng thử lại sau.'),
])
def test_chat_service_error_message(monkeypatch, headers, message):
    response = SimpleNamespace(status_code=503, headers=headers)
    monkeypatch.setattr(api_client.requests, 'post', lambda *args, **kwargs: response)

    with pytest.raises(api_client.ApiError) as exc:
        api_client.ask('Câu hỏi')
    assert str(exc.value) == message


def test_chat_recovers_from_stale_selector_label(monkeypatch):
    app_dir = Path(__file__).resolve().parents[1] / 'app'
    monkeypatch.syspath_prepend(str(app_dir))

    def request(*args, **kwargs):
        return SimpleNamespace(
            status_code=200, json=lambda: {'answer': 'Trả lời thử', 'total_tokens': 12},
        )

    monkeypatch.setattr(api_client.requests, 'post', request)
    page = AppTest.from_file(str(app_dir / 'main.py')).run()
    conversation_id = page.session_state.active_conversation_id
    for question in ('Câu hỏi 1', 'Câu hỏi 2'):
        page.chat_input[0].set_value(question).run()
        assert not page.exception

    page.session_state.active_conversation_id = NEW_CONVERSATION_TITLE
    page.chat_input[0].set_value('Câu hỏi 3').run()

    assert not page.exception
    assert page.session_state.active_conversation_id == conversation_id
    assert len(page.session_state.messages) == 6
    assert sum('Token · 12' in item.value for item in page.markdown) == 3

    page.button[0].click().run()
    new_id = page.session_state.active_conversation_id
    assert new_id != conversation_id
    page.chat_input[0].set_value('Câu hỏi 1').run()
    assert len(set(page.selectbox[0].options)) == 2

    page.selectbox[0].select_index(1).run()
    assert not page.exception
    assert page.session_state.active_conversation_id == conversation_id
    assert len(page.session_state.messages) == 6

    page.selectbox[0].select_index(0).run()
    assert not page.exception
    assert page.session_state.active_conversation_id == new_id
    assert len(page.session_state.messages) == 2
