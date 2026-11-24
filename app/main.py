'''Giao diện chat Streamlit. Chạy: streamlit run app/main.py'''
from time import perf_counter

import browser_storage
import streamlit as st
from api_client import ApiError, ask
from chat_sessions import (
    NEW_CONVERSATION_TITLE,
    conversation_title,
    create_conversation,
    delete_conversation,
    new_conversation,
    rename_conversation,
    validate_conversations,
)

FLAG_TEXT = {
    'no_citation': 'Câu trả lời chưa có nguồn dẫn được kiểm chứng.',
    'unsupported_number': 'Có con số chưa thấy trong nguồn, hãy đối chiếu với văn bản gốc.',
    'invalid_citation_removed': 'Một nguồn trích dẫn không hợp lệ đã bị gỡ.',
    'truncated': 'Câu trả lời có thể bị cắt ngắn.',
    'needs_verification': 'Nội dung này cần đơn vị có thẩm quyền xác nhận.',
    'no_valid_document_for_term': 'Kho tài liệu chưa có văn bản có hiệu lực cho học kỳ được hỏi.',
    'clarification_after_confirmation': 'Đã nhận xác nhận; kho tài liệu chưa đủ căn cứ để trả lời.',
}

st.set_page_config(page_title='Chatbot học vụ CTU', page_icon='🎓')
st.title('Chatbot tư vấn học vụ CTU')
st.caption('Câu trả lời dựa trên tài liệu đã nạp vào hệ thống. Hãy đối chiếu nguồn trích dẫn.')

storage_state = browser_storage.load_conversations()
if not isinstance(storage_state, dict) or not storage_state.get('ready'):
    st.info('Đang tải lịch sử trò chuyện từ trình duyệt...')
    st.stop()
if storage_state.get('error'):
    st.error(storage_state['error'])
    st.stop()

if 'conversations' not in st.session_state:
    persisted_state = storage_state.get('state')
    if not isinstance(persisted_state, dict):
        st.error('Dữ liệu lịch sử trò chuyện đã lưu không đúng định dạng.')
        st.stop()
    try:
        stored_conversations = validate_conversations(
            persisted_state.get('conversations', [])
        )
    except (TypeError, ValueError) as exc:
        st.error(f'Lịch sử trò chuyện đã lưu không hợp lệ: {exc}')
        st.stop()
    if stored_conversations:
        st.session_state.conversations = stored_conversations
        saved_active_id = persisted_state.get('active_conversation_id')
        conversation_ids = {
            conversation['id'] for conversation in stored_conversations
        }
        st.session_state.active_conversation_id = (
            saved_active_id
            if isinstance(saved_active_id, str)
            and saved_active_id in conversation_ids
            else stored_conversations[0]['id']
        )
    else:
        conversation = new_conversation()
        st.session_state.conversations = [conversation]
        st.session_state.active_conversation_id = conversation['id']


def start_new_conversation():
    conversations, active_id = create_conversation(
        st.session_state.conversations
    )
    st.session_state.conversations = conversations
    st.session_state.active_conversation_id = active_id


def select_conversation(conversation_id):
    st.session_state.active_conversation_id = conversation_id


def remove_conversation(conversation_id):
    conversations, active_id = delete_conversation(
        st.session_state.conversations,
        conversation_id,
        st.session_state.active_conversation_id,
    )
    st.session_state.conversations = conversations
    st.session_state.active_conversation_id = active_id
    if st.session_state.get('renaming_conversation_id') == conversation_id:
        st.session_state.renaming_conversation_id = None


def begin_rename_conversation(conversation_id):
    st.session_state.renaming_conversation_id = conversation_id
    st.session_state.rename_error = None
    st.session_state.pop(f'rename_title_{conversation_id}', None)


def save_renamed_conversation(conversation_id, title_key):
    try:
        rename_conversation(
            st.session_state.conversations,
            conversation_id,
            st.session_state.get(title_key, ''),
        )
    except ValueError as exc:
        st.session_state.rename_error = str(exc)
        return
    st.session_state.renaming_conversation_id = None
    st.session_state.rename_error = None


def cancel_rename_conversation():
    st.session_state.renaming_conversation_id = None
    st.session_state.rename_error = None


conversation_by_id = {
    conversation['id']: conversation
    for conversation in st.session_state.conversations
}
active_id = st.session_state.active_conversation_id
if active_id not in conversation_by_id:
    active_id = next(iter(conversation_by_id))


with st.sidebar:
    st.button(
        'Cuộc hội thoại mới',
        on_click=start_new_conversation,
        use_container_width=True,
    )
    st.markdown('**Các cuộc hội thoại**')
    for conversation_id, conversation in conversation_by_id.items():
        with st.container():
            row = st.columns([0.82, 0.18], vertical_alignment='center')
            row[0].button(
                conversation['title'],
                key=f'conversation_{conversation_id}',
                type='primary' if conversation_id == active_id else 'secondary',
                use_container_width=True,
                on_click=select_conversation,
                args=(conversation_id,),
            )
            with row[1].popover('⋮', help='Tùy chọn cuộc hội thoại'):
                if (
                    st.session_state.get('renaming_conversation_id')
                    == conversation_id
                ):
                    title_key = f'rename_title_{conversation_id}'
                    with st.form(f'rename_form_{conversation_id}'):
                        st.text_input(
                            'Tên mới',
                            value=conversation['title'],
                            key=title_key,
                            max_chars=80,
                        )
                        if error := st.session_state.get('rename_error'):
                            st.error(error)
                        save_col, cancel_col = st.columns(2)
                        save_col.form_submit_button(
                            'Lưu',
                            type='primary',
                            use_container_width=True,
                            on_click=save_renamed_conversation,
                            args=(conversation_id, title_key),
                        )
                        cancel_col.form_submit_button(
                            'Hủy',
                            use_container_width=True,
                            on_click=cancel_rename_conversation,
                        )
                else:
                    st.button(
                        'Đổi tên',
                        key=f'rename_conversation_{conversation_id}',
                        use_container_width=True,
                        on_click=begin_rename_conversation,
                        args=(conversation_id,),
                    )
                    st.button(
                        'Xóa',
                        key=f'delete_conversation_{conversation_id}',
                        type='secondary',
                        use_container_width=True,
                        on_click=remove_conversation,
                        args=(conversation_id,),
                    )

st.session_state.active_conversation_id = active_id
active_conversation = conversation_by_id[active_id]
st.session_state.messages = active_conversation['messages']


def render(msg):
    st.markdown(msg['content'])
    d = msg.get('data') or {}
    if (seconds := msg.get('response_seconds')) is not None:
        tokens = d.get('total_tokens')
        with st.container(horizontal=True, gap='small'):
            st.badge(f'Thời gian phản hồi · {seconds:.2f} s', color='blue')
            st.badge(
                f'Token · {tokens:,}' if tokens is not None else 'Token · Chưa có dữ liệu',
                color='violet',
            )
    if d.get('need_clarification'):
        st.info('Chatbot cần thêm thông tin để trả lời chính xác.')
    if d.get('abstain'):
        st.warning('Chưa đủ căn cứ trong kho tài liệu để xác nhận nội dung này.')
    for flag in (d.get('risk_flag') or '').split(','):
        if flag in FLAG_TEXT:
            st.caption('Lưu ý: ' + FLAG_TEXT[flag])
    cites = d.get('citations') or []
    if cites:
        with st.expander(f'Nguồn trích dẫn ({len(cites)})'):
            for c in cites:
                page = f"trang {c['page']}" if c.get('page') else None
                loc = ', '.join(x for x in [c.get('section'), page] if x)
                st.markdown(f"**[{c['source_id']}]** {c['document']}" + (f' ({loc})' if loc else ''))
                if c.get('url'):
                    st.markdown(c['url'])


for m in st.session_state.messages:
    with st.chat_message(m['role']):
        render(m)

if q := st.chat_input('Nhập câu hỏi về quy chế học vụ...'):
    history = [
        {
            'role': message['role'],
            'content': message['content'][:2000],
            'need_clarification': bool(
                (message.get('data') or {}).get('need_clarification')
            ),
        }
        for message in active_conversation['messages'][-6:]
    ]
    active_conversation['messages'].append({'role': 'user', 'content': q})
    if active_conversation['title'] == NEW_CONVERSATION_TITLE:
        active_conversation['title'] = conversation_title(q)
    with st.chat_message('user'):
        st.markdown(q)
    with st.chat_message('assistant'):
        with st.spinner('Đang tra cứu tài liệu...'):
            try:
                started = perf_counter()
                data = ask(q, history)
                msg = {
                    'role': 'assistant', 'content': data['answer'], 'data': data,
                    'response_seconds': perf_counter() - started,
                }
            except ApiError as e:
                msg = {'role': 'assistant', 'content': str(e)}
        render(msg)
    active_conversation['messages'].append(msg)

save_state = browser_storage.save_conversations(
    st.session_state.conversations,
    st.session_state.active_conversation_id,
    enabled=True,
)
if isinstance(save_state, dict) and save_state.get('error'):
    st.error(save_state['error'])
