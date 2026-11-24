# TV4 – LLM & ứng dụng: cách chạy

Nhánh `feat/llm-app-tv4`. Phạm vi: B7 (Groq), B8 (kiểm trích dẫn + API), B9 (Streamlit) theo runbook §10–12.

## Chạy độc lập, chưa cần Qdrant/TV3

```bash
python -m venv .venv && source .venv/bin/activate
pip install groq fastapi "uvicorn[standard]" pydantic streamlit requests python-dotenv pytest httpx ruff
cp .env.example .env            # điền GROQ_API_KEY, giữ RETRIEVER=mock
pytest -q                       # 25 test, không tốn quota
python -m scripts.smoke_groq    # T2 phần Groq, tốn 1 request
python -m scripts.ask_cli "Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?"
uvicorn backend.main:app --host 127.0.0.1 --port 8000     # cửa sổ 1
streamlit run app/main.py                                 # cửa sổ 2
```

`RETRIEVER=mock` dùng `backend/services/retriever_mock.py`: 3 đoạn **dữ liệu giả** (gắn nhãn `[DỮ LIỆU GIẢ]`,
số hiệu `QĐ-MOCK`), chỉ để thử luồng, không dùng để đánh giá.

## Ranh giới với TV3

- TV4 chỉ gọi `backend/services/retrieval.py::retrieve(question)`; không truy vấn Qdrant.
- Khi TV3 xong `backend/services/retriever.py` (runbook §9.2), đặt `RETRIEVER=real` là chạy, không sửa code TV4.
- Đối tượng trả về cần có: `routed.term_key`, `evidence: list[EvidenceChunk]`, `n_candidates`, `top_score`.
- `format_evidence()` đặt ở `generator.py` (việc của prompt). TV3 có thể import từ đây thay vì viết lại trong reranker.

## Hội thoại làm rõ

`POST /chat` nhận tối đa 6 lượt history gần nhất. Streamlit gửi lịch sử này nhưng API chỉ ghép
ngữ cảnh vào câu hỏi khi lượt assistant ngay trước đó có `need_clarification=true`; câu hỏi mới
sau một câu trả lời hoàn tất vẫn được xử lý độc lập. Ngữ cảnh ghép được dùng cho cả retrieval
và generation, nên câu trả lời như “khóa 47” có thể tiếp tục câu hỏi vừa làm rõ. Lịch sử hội thoại
được lưu trong localStorage của browser profile nên còn sau khi refresh trang. “Cuộc hội thoại mới”
tạo phiên riêng; nút “⋮” cạnh từng phiên mở tùy chọn đổi tên hoặc xóa cuộc hội thoại đó. Lịch sử
không đồng bộ giữa trình duyệt/thiết bị và sẽ mất nếu người dùng xóa dữ liệu trang web của trình duyệt.

## Trạng thái kiểm thử

| Mã | Nội dung | Trạng thái |
|---|---|---|
| T11 | groq_client + generator (mock) | Đạt (pytest) |
| T12 | citation_validator | Đạt (pytest) |
| T13 | API /chat (mock) | Đạt (pytest) |
| T2 (Groq) | model ID + gọi thật | Chờ khoá API |
| T14, T16, T19 | ca đặc biệt, UI, đo token | Cần Groq thật, và T14 cần corpus thật |
