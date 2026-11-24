"""Browser localStorage bridge for chat history."""

from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    'ctu_chat_history_storage',
    path=str(Path(__file__).with_name('chat_history_storage')),
)
_STORAGE_KEY = 'ctu-rag-chatbot:conversations:v1'


def load_conversations():
    return _component(
        mode='load',
        storage_key=_STORAGE_KEY,
        default=None,
        key='chat_history_storage_load',
    )


def save_conversations(conversations, active_id: str, enabled: bool):
    return _component(
        mode='save',
        storage_key=_STORAGE_KEY,
        state={
            'conversations': conversations,
            'active_conversation_id': active_id,
        },
        enabled=enabled,
        default=None,
        key='chat_history_storage_save',
    )
