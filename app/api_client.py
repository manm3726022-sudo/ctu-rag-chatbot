'''Giao diện chỉ gọi FastAPI, không gọi Groq và không đọc khoá API (runbook §12).'''
import os

import requests
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv('API_URL', 'http://localhost:8000')


class ApiError(Exception):
    pass


def ask(question: str, history: list[dict] | None = None) -> dict:
    try:
        r = requests.post(
            f'{API_URL}/chat',
            json={'question': question, 'history': history or []},
            timeout=90,
        )
    except requests.RequestException:
        raise ApiError('Không kết nối được máy chủ trả lời. Vui lòng thử lại sau.')
    if r.status_code == 503:
        delay = r.headers.get('Retry-After', '')
        if delay.isdecimal():
            raise ApiError(f'Đã chạm hạn mức token. Vui lòng thử lại sau {delay} giây.')
        raise ApiError('Dịch vụ trả lời tạm thời không khả dụng. Vui lòng thử lại sau.')
    if r.status_code == 422:
        raise ApiError('Câu hỏi trống hoặc dài quá 1.000 ký tự.')
    if r.status_code != 200:
        raise ApiError('Có lỗi khi xử lý câu hỏi.')
    return r.json()
