'''Giao diện chat Streamlit. Chạy: streamlit run app/main.py'''
import streamlit as st
from api_client import ApiError, ask
from chat_sessions import (
    MAX_ARCHIVED_CONVERSATIONS,
    NEW_CONVERSATION_TITLE,
    conversation_title,
    create_conversation,
    new_conversation,
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

if 'conversations' not in st.session_state:
    existing_messages = st.session_state.get('messages', [])
    conversation = new_conversation()
    conversation['messages'] = existing_messages
    st.session_state.conversations = [conversation]
    st.session_state.active_conversation_id = conversation['id']

conversation_by_id = {
    conversation['id']: conversation
    for conversation in st.session_state.conversations
}
active_id = st.session_state.active_conversation_id
active_conversation = conversation_by_id[active_id]
st.session_state.messages = active_conversation['messages']


def activate_selected_conversation():
    st.session_state.active_conversation_id = st.session_state.conversation_selector


with st.sidebar:
    if st.button('Cuộc hội thoại mới') and active_conversation['messages']:
        conversations, active_id = create_conversation(
            st.session_state.conversations,
            active_id=st.session_state.active_conversation_id,
            max_archived=MAX_ARCHIVED_CONVERSATIONS,
        )
        st.session_state.conversations = conversations
        st.session_state.active_conversation_id = active_id
        st.session_state.conversation_selector = active_id
        st.rerun()
    conversation_ids = [conversation['id'] for conversation in st.session_state.conversations]
    st.selectbox(
        'Các cuộc hội thoại',
        options=conversation_ids,
        format_func=lambda conversation_id: conversation_by_id[conversation_id]['title'],
        key='conversation_selector',
        on_change=activate_selected_conversation,
    )


def render(msg):
    st.markdown(msg['content'])
    d = msg.get('data') or {}
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
                data = ask(q, history)
                msg = {'role': 'assistant', 'content': data['answer'], 'data': data}
            except ApiError as e:
                msg = {'role': 'assistant', 'content': str(e)}
        render(msg)
    active_conversation['messages'].append(msg)
