# Created: 2026-09-29 11:59
"""OpenRouter chat/completions 호출: 재시도, 오류 분류, 응답에서 JSON 뽑기.

키는 config.get_api_key()로만 읽고, 오류 메시지에 키를 넣지 않음.
"""
import json
import re
import time
import urllib.error
import urllib.request

from config import OPENROUTER_BASE_URL, get_api_key

RETRY_CODES = (429, 502, 503)
RETRY_WAITS = (10, 20, 40, 80)  # 무료 모델은 공용 한도(429)나 과부하(502/503)가 잦음


class OpenRouterError(Exception):
    """kind: rate_limited(재시도해도 한도 초과) | upstream_error | empty(빈 응답)"""

    def __init__(self, kind, message, finish_reason=None):
        super().__init__(message)
        self.kind = kind
        self.finish_reason = finish_reason


def _post(body, timeout):
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {get_api_key()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except (urllib.error.URLError, TimeoutError) as e:
        return None, str(e)
    # 제공사 오류는 HTTP 200 본문의 "error"로 오기도 함 (예: 503 과부하)
    if "error" in data:
        return data["error"].get("code"), data["error"]
    return 200, data


def chat_events(model, content, max_tokens=300, timeout=120, waits=RETRY_WAITS, extra=None):
    """진행 상황을 이벤트로 내보내는 제너레이터.

    ("retry", {"attempt", "max", "wait", "code"})를 0번 이상 내보낸 뒤
    ("done", {"content", "usage", "finish_reason"})로 끝남. 실패하면 OpenRouterError.
    waits: 재시도 사이 대기 초 목록 (대체 모델이 있으면 짧게 줘서 빨리 넘어감)
    extra: 요청 본문에 더할 필드 (예: {"reasoning": {"enabled": False}})
    """
    body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens, **(extra or {})}
    for attempt in range(len(waits) + 1):
        code, payload = _post(body, timeout)
        if code == 200:
            choice = payload["choices"][0]
            text = (choice["message"].get("content") or "").strip()
            if not text:
                # 추론 모델은 max_tokens를 추론에 다 써 버리면 content가 비어서 옴
                raise OpenRouterError("empty", "모델이 빈 응답을 돌려주었습니다.", choice.get("finish_reason"))
            yield "done", {"content": text, "usage": payload.get("usage", {}),
                           "finish_reason": choice.get("finish_reason")}
            return
        if code in RETRY_CODES and attempt < len(waits):
            wait = waits[attempt]
            yield "retry", {"attempt": attempt + 1, "max": len(waits), "wait": wait, "code": code}
            time.sleep(wait)
            continue
        if code == 429:
            raise OpenRouterError("rate_limited", f"HTTP 429: {payload}")
        raise OpenRouterError("upstream_error", f"HTTP {code}: {payload}")


def chat(model, content, max_tokens=300, timeout=120, on_retry=None, waits=RETRY_WAITS):
    """chat_events를 끝까지 돌려 (content, usage, 걸린 초)를 돌려줌."""
    start = time.perf_counter()
    for kind, info in chat_events(model, content, max_tokens, timeout, waits):
        if kind == "retry" and on_retry:
            on_retry(info)
        elif kind == "done":
            return info["content"], info["usage"], time.perf_counter() - start


def extract_json(text):
    """모델 응답에서 JSON 객체를 뽑음. ```json 코드 블록이나 앞뒤 설명이 붙어 와도 처리. 실패하면 ValueError."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("응답에 JSON 객체가 없습니다.")
    return json.loads(text[start:end + 1])
