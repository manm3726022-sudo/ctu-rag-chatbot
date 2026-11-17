'''T2 (phần Groq): kiểm model ID còn hoạt động và gọi thử một lần. Chạy: python -m scripts.smoke_groq
Tốn đúng 1 request. Phần BGE-M3/Qdrant của T2 do TV3 kiểm.'''
from groq import Groq

from core import config


def main():
    if not config.GROQ_API_KEY:
        raise SystemExit('Chưa có GROQ_API_KEY trong .env (cp .env.example .env rồi điền khoá).')
    client = Groq(api_key=config.GROQ_API_KEY, timeout=30.0)
    ids = {m.id for m in client.models.list().data}
    for name, mid in (('GROQ_MODEL', config.GROQ_MODEL), ('GROQ_FALLBACK_MODEL', config.GROQ_FALLBACK_MODEL)):
        print(f'{name} = {mid}:', 'CÓ' if mid in ids else 'KHÔNG THẤY -> sửa .env')
    raw = client.chat.completions.with_raw_response.create(
        model=config.GROQ_MODEL,
        messages=[{'role': 'user', 'content': 'Trả lời đúng một từ: xin chào'}],
        max_completion_tokens=200, reasoning_effort='low', include_reasoning=False)
    r = raw.parse()
    print('Trả lời:', r.choices[0].message.content)
    print('finish_reason:', r.choices[0].finish_reason, '| usage:', r.usage)
    for k, v in raw.headers.items():
        if k.lower().startswith('x-ratelimit') or k.lower() == 'retry-after':
            print(k, '=', v)


if __name__ == '__main__':
    main()
