from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from app import api_client
from app.chat_sessions import (
    NEW_CONVERSATION_TITLE,
    conversation_title,
    create_conversation,
    delete_conversation,
    rename_conversation,
    validate_conversations,
)


def test_create_conversation_keeps_all_existing_conversations():
    existing = [
        {'id': str(index), 'title': f'Chat {index}', 'messages': [{'content': str(index)}]}
        for index in range(8)
    ]

    conversations, active_id = create_conversation(existing)

    assert len(conversations) == len(existing) + 1
    assert conversations[0]['id'] == active_id
    assert conversations[0]['messages'] == []
    assert [conversation['id'] for conversation in conversations[1:]] == [
        str(index) for index in range(8)
    ]
    assert conversations[1]['messages'] == [{'content': '0'}]


@pytest.mark.parametrize(
    ('active_id', 'expected_active'),
    [('0', '1'), ('1', '1'), ('missing', '1')],
)
def test_delete_conversation_removes_only_selected_item_and_selects_valid_active(
    active_id, expected_active
):
    existing = [
        {'id': str(index), 'title': f'Chat {index}', 'messages': []}
        for index in range(3)
    ]

    conversations, new_active = delete_conversation(existing, '0', active_id)

    assert [conversation['id'] for conversation in conversations] == ['1', '2']
    assert new_active == expected_active


def test_deleting_last_conversation_creates_an_empty_active_conversation():
    conversations, active_id = delete_conversation(
        [{'id': 'only', 'title': 'Only', 'messages': [{'content': 'saved'}]}],
        'only',
        'only',
    )

    assert len(conversations) == 1
    assert conversations[0]['id'] == active_id
    assert conversations[0]['messages'] == []


def test_rename_conversation_changes_only_the_selected_title():
    conversations = [
        {'id': 'first', 'title': 'First', 'messages': [{'content': 'kept'}]},
        {'id': 'second', 'title': 'Second', 'messages': []},
    ]

    rename_conversation(conversations, 'first', '  New title  ')

    assert conversations[0]['title'] == 'New title'
    assert conversations[0]['messages'] == [{'content': 'kept'}]
    assert conversations[1]['title'] == 'Second'


def test_rename_conversation_rejects_empty_titles():
    with pytest.raises(ValueError, match='không được để trống'):
        rename_conversation(
            [{'id': 'first', 'title': 'First', 'messages': []}],
            'first',
            '   ',
        )


def test_validate_conversations_rejects_malformed_saved_messages():
    with pytest.raises(ValueError, match='tin nhắn'):
        validate_conversations([
            {
                'id': 'one',
                'title': 'Chat',
                'messages': [{'role': 'system', 'content': 'not supported'}],
            }
        ])


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


def test_chat_keeps_conversations_available_for_selection(monkeypatch):
    app_dir = Path(__file__).resolve().parents[1] / 'app'
    monkeypatch.syspath_prepend(str(app_dir))
    import browser_storage

    monkeypatch.setattr(
        browser_storage,
        'load_conversations',
        lambda: {'ready': True, 'state': {'conversations': []}},
    )
    monkeypatch.setattr(
        browser_storage,
        'save_conversations',
        lambda conversations, active_id, enabled: None,
    )

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

    page.button[0].click().run()
    new_id = page.session_state.active_conversation_id
    assert new_id != conversation_id
    page.chat_input[0].set_value('Câu hỏi 3').run()

    assert not page.exception
    assert page.session_state.active_conversation_id == new_id
    assert len(page.session_state.messages) == 2
    assert sum('Token · 12' in item.value for item in page.markdown) == 1

    assert len(page.session_state.conversations) == 2
    page.button(key=f'conversation_{conversation_id}').click().run()
    assert page.session_state.active_conversation_id == conversation_id
    assert len(page.session_state.messages) == 4
