"""Local admin UI for uploading sources and reviewing indexed chunks."""

import hmac
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import requests
import streamlit as st
from pydantic import ValidationError
from qdrant_client.http.exceptions import UnexpectedResponse

from app import admin_service
from core import config

ADMIN_ERRORS = (
    ImportError,
    KeyError,
    OSError,
    RuntimeError,
    subprocess.TimeoutExpired,
    TypeError,
    UnexpectedResponse,
    ValidationError,
    ValueError,
    httpx.HTTPError,
    json.JSONDecodeError,
    requests.RequestException,
)


def show_source_page(chunk):
    source_path = chunk["source_path"]
    if not source_path.exists():
        st.warning("Không tìm thấy tệp nguồn trên máy chủ.")
        return
    if source_path.suffix.lower() == ".pdf":
        from pypdfium2 import PdfDocument

        with PdfDocument(source_path) as document:
            page_start = chunk["page_start"]
            page_end = chunk["page_end"]
            if page_start < 1 or page_end > len(document):
                st.warning("Số trang của đoạn nằm ngoài phạm vi PDF.")
                return
            for page_number in range(page_start, page_end + 1):
                page = document[page_number - 1]
                bitmap = page.render(scale=1.25)
                image = bitmap.to_pil()
                st.image(image, caption=f"Trang {page_number} của tài liệu gốc")
                bitmap.close()
                page.close()
    else:
        st.download_button(
            "Tải DOCX nguồn để đối chiếu",
            data=source_path.read_bytes(),
            file_name=source_path.name,
            key=f"download_source_{chunk['chunk_id']}",
        )


st.set_page_config(page_title="Admin tài liệu CTU", page_icon="🛠️")
st.title("Quản trị kho tài liệu CTU")
st.caption("Tải tài liệu, kiểm tra các đoạn trích và quản lý nội dung đã duyệt.")

if not config.ADMIN_PASSWORD:
    st.error("Giao diện admin đang khóa. Hãy cấu hình ADMIN_PASSWORD trong .env rồi khởi động lại.")
    st.stop()

if not st.session_state.get("admin_authenticated"):
    with st.form("admin_login"):
        password = st.text_input("Mật khẩu admin", type="password")
        submitted = st.form_submit_button("Đăng nhập")
    if submitted:
        if hmac.compare_digest(
            password.encode("utf-8"), config.ADMIN_PASSWORD.encode("utf-8")
        ):
            st.session_state.admin_authenticated = True
            st.rerun()
        st.error("Mật khẩu không chính xác.")
    st.stop()

with st.sidebar:
    reviewer = st.text_input("Tên người duyệt / chỉnh sửa", value="Admin")
    if st.button("Đăng xuất"):
        st.session_state.admin_authenticated = False
        st.rerun()

upload_tab, pending_tab, approved_tab = st.tabs(
    ["Tải tài liệu", "Pending review", "Approved"]
)

with upload_tab:
    st.subheader("Tải lên và xử lý tài liệu")
    st.caption(
        "MVP nhận PDF hoặc DOCX. Tài liệu mới được lập chỉ mục ở trạng thái pending; "
        "không tự động được phép dùng để trả lời."
    )
    uploaded = st.file_uploader("Tệp nguồn", type=["pdf", "docx"])
    extension = Path(uploaded.name).suffix.lower() if uploaded else ".pdf"
    source_kind_options = list(
        admin_service.UPLOAD_TYPES.get(extension, {"pdf_text"})
    )
    with st.form("upload_document", clear_on_submit=True):
        source_kind = st.selectbox(
            "Kiểu nguồn",
            source_kind_options,
            help="PDF text vẫn tự OCR các trang không trích xuất được chữ.",
        )
        document_id = st.text_input("Mã văn bản", placeholder="qd9999")
        document_number = st.text_input(
            "Số hiệu", placeholder="9999/QĐ-ĐHCT"
        )
        title = st.text_input("Tên văn bản")
        issuer = st.text_input("Cơ quan ban hành", value="Đại học Cần Thơ")
        issued_on = st.date_input("Ngày ban hành")
        effective_date = st.text_input(
            "Ngày hiệu lực (YYYY-MM-DD, nếu có)", placeholder="2026-09-01"
        )
        effective_from_term = st.text_input(
            "Học kỳ bắt đầu hiệu lực (nếu có)", placeholder="2026-HK1"
        )
        effective_until_term = st.text_input(
            "Học kỳ kết thúc hiệu lực, không bao gồm (nếu có)",
            placeholder="2028-HK1",
        )
        applicability = st.text_area(
            "Phạm vi áp dụng", placeholder="Sinh viên đại học chính quy..."
        )
        submitted = st.form_submit_button("Tải lên và chạy xử lý")

    if submitted:
        if uploaded is None:
            st.error("Hãy chọn một tệp trước khi gửi.")
        elif not reviewer.strip():
            st.error("Hãy nhập tên admin ở thanh bên.")
        else:
            metadata = {
                "document_id": document_id,
                "document_number": document_number,
                "title": title,
                "issuer": issuer,
                "issued_on": issued_on.isoformat(),
                "effective_date": effective_date,
                "effective_from_term": effective_from_term,
                "effective_until_term_exclusive": effective_until_term,
                "applicability": applicability,
                "source_kind": source_kind,
            }
            try:
                document = admin_service.register_uploaded_document(
                    metadata, uploaded.name, uploaded.getvalue()
                )
                with st.spinner("Đang trích xuất/OCR, chia đoạn, embedding và lập chỉ mục..."):
                    count = admin_service.process_document(document["document_id"])
                st.success(
                    f"Đã xử lý {document['document_number']}: lập chỉ mục {count} đoạn. "
                    "Các đoạn đang ở trạng thái pending."
                )
                st.rerun()
            except ADMIN_ERRORS as exc:
                st.error(f"Không xử lý được tài liệu: {type(exc).__name__}: {exc}")

    st.subheader("Tài liệu cần xử lý lại")
    registered = admin_service.list_registered_documents()
    if registered:
        registered_by_id = {row["document_id"]: row for row in registered}
        selected_document = st.selectbox(
            "Tài liệu đã upload nhưng chưa xử lý xong",
            list(registered_by_id),
            format_func=lambda document_id: (
                f"{registered_by_id[document_id]['document_number']} — "
                f"{registered_by_id[document_id]['title']}"
            ),
        )
        if st.button("Chạy lại OCR và lập chỉ mục", key="retry_ingestion"):
            try:
                with st.spinner("Đang chạy lại pipeline..."):
                    count = admin_service.process_document(
                        selected_document
                    )
                st.success(f"Đã lập chỉ mục {count} đoạn.")
                st.rerun()
            except ADMIN_ERRORS as exc:
                st.error(f"Không xử lý được: {type(exc).__name__}: {exc}")
    else:
        st.info("Không có tài liệu nào đang chờ xử lý.")

with pending_tab:
    pending = admin_service.list_review_chunks("pending")
    document_options = ["Tất cả"] + sorted(
        {chunk["document_id"] for chunk in pending}
    )
    selected_pending_doc = st.selectbox(
        "Lọc pending theo văn bản",
        document_options,
        key="pending_document_filter",
    )
    visible_pending = [
        chunk
        for chunk in pending
        if selected_pending_doc == "Tất cả"
        or chunk["document_id"] == selected_pending_doc
    ]
    st.write(f"Còn **{len(visible_pending)}** đoạn pending trong phạm vi đang chọn.")
    with st.form("approve_all_form", clear_on_submit=True):
        confirm_all = st.checkbox(
            "Tôi đã kiểm tra nội dung và xác nhận toàn bộ các đoạn đang hiển thị đều chính xác"
        )
        approve_all = st.form_submit_button(
            f"Approve all — duyệt {len(visible_pending)} đoạn đang hiển thị",
            disabled=not visible_pending or not reviewer.strip(),
        )
    if approve_all:
        if not confirm_all:
            st.error("Hãy xác nhận đã kiểm tra các đoạn trước khi duyệt hàng loạt.")
        else:
            try:
                count = admin_service.approve_chunks(
                    [str(chunk["chunk_id"]) for chunk in visible_pending],
                    reviewer,
                )
                st.success(f"Đã duyệt {count} đoạn.")
                st.rerun()
            except ADMIN_ERRORS as exc:
                st.error(f"Không duyệt được: {type(exc).__name__}: {exc}")

    for chunk in visible_pending:
        with st.expander(
            f"{chunk['document_number']} · {chunk['section']} · "
            f"trang {chunk['page_start']}-{chunk['page_end']}"
        ):
            st.caption(f"Chunk ID: {chunk['chunk_id']}")
            st.text(chunk["content"])
            if st.checkbox(
                "Đối chiếu với tệp nguồn",
                key=f"show_source_{chunk['chunk_id']}",
            ):
                show_source_page(chunk)
            if st.button(
                "Approve đoạn này",
                key=f"approve_{chunk['chunk_id']}",
                disabled=not reviewer.strip(),
            ):
                try:
                    admin_service.approve_chunks([str(chunk["chunk_id"])], reviewer)
                    st.success("Đã duyệt đoạn.")
                    st.rerun()
                except ADMIN_ERRORS as exc:
                    st.error(f"Không duyệt được: {type(exc).__name__}: {exc}")

with approved_tab:
    checked = admin_service.list_review_chunks("checked")
    document_options = ["Tất cả"] + sorted(
        {chunk["document_id"] for chunk in checked}
    )
    selected_checked_doc = st.selectbox(
        "Lọc approved theo văn bản",
        document_options,
        key="approved_document_filter",
    )
    visible_checked = [
        chunk
        for chunk in checked
        if selected_checked_doc == "Tất cả"
        or chunk["document_id"] == selected_checked_doc
    ]
    st.write(f"Có **{len(visible_checked)}** đoạn approved trong phạm vi đang chọn.")
    if visible_checked:
        checked_by_id = {
            str(chunk["chunk_id"]): chunk for chunk in visible_checked
        }
        selected_chunk = st.selectbox(
            "Chọn đoạn để xem hoặc chỉnh sửa",
            list(checked_by_id),
            format_func=lambda chunk_id: (
                f"{checked_by_id[chunk_id]['document_number']} · "
                f"{checked_by_id[chunk_id]['section']} · "
                f"trang {checked_by_id[chunk_id]['page_start']}-"
                f"{checked_by_id[chunk_id]['page_end']} · "
                f"{checked_by_id[chunk_id]['content'][:70].replace(chr(10), ' ')}"
            ),
            key="approved_chunk_selector",
        )
        selected_chunk = checked_by_id[selected_chunk]
        st.caption(
            f"{selected_chunk['document_title']} · {selected_chunk['section']} · "
            f"trang {selected_chunk['page_start']}-{selected_chunk['page_end']} · "
            f"Chunk ID: {selected_chunk['chunk_id']}"
        )
        if st.checkbox(
            "Đối chiếu với tệp nguồn",
            key=f"show_source_{selected_chunk['chunk_id']}",
        ):
            show_source_page(selected_chunk)
        with st.form("edit_approved_chunk"):
            edited_content = st.text_area(
                "Nội dung đoạn đã approved",
                value=selected_chunk["content"],
                height=240,
                key=f"edit_content_{selected_chunk['chunk_id']}",
            )
            save_edit = st.form_submit_button(
                "Lưu chỉnh sửa và tái lập chỉ mục",
                disabled=not reviewer.strip(),
            )
        if save_edit:
            try:
                with st.spinner(
                    "Đang lưu bản sửa và cập nhật embedding/Qdrant cho đoạn này..."
                ):
                    new_id = admin_service.edit_approved_chunk(
                        str(selected_chunk["chunk_id"]),
                        edited_content,
                        reviewer,
                    )
                st.success(f"Đã lưu và cập nhật chỉ mục. Chunk ID mới: {new_id}")
                st.rerun()
            except ADMIN_ERRORS as exc:
                st.error(f"Không cập nhật được: {type(exc).__name__}: {exc}")
    else:
        st.info("Chưa có đoạn approved trong phạm vi đang chọn.")
