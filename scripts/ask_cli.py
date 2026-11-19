'''Hỏi thử từ dòng lệnh, không cần FastAPI/Streamlit: python -m scripts.ask_cli "câu hỏi"
Tốn 1–2 request Groq.'''
import json
import sys

from fastapi.testclient import TestClient

from backend.main import app

if __name__ == '__main__':
    q = ' '.join(sys.argv[1:]) or 'Mỗi học kỳ được đăng ký tối đa bao nhiêu tín chỉ?'
    with TestClient(app) as c:
        r = c.post('/chat', json={'question': q})
        print(r.status_code)
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
