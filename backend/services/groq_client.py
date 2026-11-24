'''Gọi GroqCloud Free API: giữ ngân sách token/phút, xử lý 429/timeout/model lỗi, chuyển model dự phòng.
Không có đường nào gọi dịch vụ trả phí (runbook §10.2, quyết định D1).'''
import time
from collections import deque
from math import ceil

import groq
from groq import Groq

from core import config


class QuotaExhausted(Exception):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class LLMUnavailable(Exception):
    pass


MAX_WAIT_S = 25
_client = None


def _get():
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise LLMUnavailable('Chưa cấu hình GROQ_API_KEY trong .env')
        _client = Groq(api_key=config.GROQ_API_KEY, timeout=config.GROQ_TIMEOUT_S, max_retries=0)
    return _client


class TpmLimiter:
    '''Cửa sổ trượt 60 giây, tính theo token ước lượng (đầu vào + đầu ra tối đa).'''

    def __init__(self, budget: int):
        self.budget, self.events = budget, deque()

    def wait_time(self, need: int, now: float) -> float:
        while self.events and now - self.events[0][0] >= 60:
            self.events.popleft()
        remaining = sum(tokens for _, tokens in self.events)
        if remaining + need <= self.budget:
            return 0.0
        for recorded_at, tokens in self.events:
            remaining -= tokens
            if remaining == 0 or remaining + need <= self.budget:
                return 60 - (now - recorded_at)
        return 0.0

    def record(self, need: int, now: float):
        self.events.append((now, need))


limiter = TpmLimiter(config.GROQ_TPM_BUDGET)


def _retry_after(e):
    try:
        return float(e.response.headers.get('retry-after'))
    except (AttributeError, TypeError, ValueError):
        return None


def chat(messages, est_tokens: int, sleep=time.sleep):
    '''Gọi Chat Completions. Ném QuotaExhausted hoặc LLMUnavailable khi không còn cách nào.'''
    wait = limiter.wait_time(est_tokens, time.monotonic())
    if wait > MAX_WAIT_S:
        delay = ceil(wait)
        raise QuotaExhausted(f'Đang vượt ngân sách token mỗi phút, thử lại sau {delay} giây', delay)
    if wait > 0:
        sleep(wait)
    limiter.record(est_tokens, time.monotonic())
    last = None
    for model in (config.GROQ_MODEL, config.GROQ_FALLBACK_MODEL):
        for _ in range(2):
            try:
                return _get().chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_completion_tokens=config.GROQ_MAX_OUTPUT_TOKENS,
                    reasoning_effort='low',
                    include_reasoning=False,
                )
            except groq.RateLimitError as e:
                last, ra = e, _retry_after(e)
                if ra is not None and ra > 60:  # nhiều khả năng hết quota ngày của model này
                    break
                sleep(min(ra or 5, 30))
            except (groq.APITimeoutError, groq.APIConnectionError) as e:
                last = e
                sleep(2)
            except (groq.NotFoundError, groq.BadRequestError) as e:  # model ID sai hoặc ngừng hoạt động
                last = e
                break
    if isinstance(last, groq.RateLimitError):
        raise QuotaExhausted('Đã hết hạn mức GroqCloud Free, vui lòng thử lại sau')
    raise LLMUnavailable(f'Không gọi được Groq: {type(last).__name__}')
