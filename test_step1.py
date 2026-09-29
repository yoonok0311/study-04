# Created: 2026-09-29 12:03
"""1단계(재료 인식) 서버 테스트. 서버를 따로 켤 필요 없음 (Flask test_client).

py test_step1.py          # API를 부르지 않는 검사 (입력 검증, 응답 해석, 오류 처리, 캐시)
py test_step1.py --live   # 위 검사 + samples/ 사진으로 실제 모델 호출 (무료 호출 한도를 사진당 1~5회 씀)
"""
import io
import json
import sys
from pathlib import Path

from PIL import Image

import app as server
from openrouter import OpenRouterError, extract_json

SAMPLES = Path(__file__).resolve().parent / "samples"
client = server.app.test_client()
failures = []


def check(name, condition, detail=""):
    print(f"  {'통과' if condition else '실패'}  {name}" + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def image_bytes(fmt="JPEG", size=(64, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return buffer.getvalue()


def post(data, filename="fridge.jpg"):
    response = client.post("/api/ingredients", data={"image": (io.BytesIO(data), filename)},
                           content_type="multipart/form-data")
    if response.mimetype == "application/x-ndjson":
        return response.status_code, [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
    return response.status_code, response.get_json()


def fake_chat(*replies):
    """chat_events 대신 쓸 가짜: 부를 때마다 replies를 차례로 돌려줌 (예외면 raise)."""
    calls = []

    def events(model, content, max_tokens=300, timeout=120):
        reply = replies[len(calls)]
        calls.append(max_tokens)
        if isinstance(reply, Exception):
            raise reply
        yield "done", {"content": reply, "usage": {}, "finish_reason": "stop"}

    return events, calls


def offline_tests():
    print("[입력 검증]")
    status, body = client.post("/api/ingredients").status_code, None
    check("이미지 없음 → 400", status == 400)
    status, body = post(b"hello, not an image", "fake.jpg")
    check("이미지가 아닌 파일(확장자만 .jpg) → 400 bad_image", status == 400 and body["code"] == "bad_image")
    status, body = post(image_bytes("GIF"), "a.gif")
    check("GIF → 400 bad_image", status == 400 and body["code"] == "bad_image")
    status, body = post(b"\xff" * (server.MAX_IMAGE_BYTES + 1))
    check("5MB 초과 → 400/413", status in (400, 413) and body["code"] == "bad_image", str(status))
    check("index.html 제공", client.get("/").status_code == 200)

    print("[응답 해석]")
    check("```json 코드 블록", extract_json('설명\n```json\n{"a": 1}\n```')["a"] == 1)
    check("앞뒤에 설명이 붙은 JSON", extract_json('결과: {"a": {"b": 2}} 끝')["a"]["b"] == 2)
    result = server.normalize({"ingredients": [
        {"name": "달걀", "quantity": "", "category": "유제품/달걀", "confidence": "low"},
        {"name": "달 걀", "quantity": "6개", "category": "유제품/달걀", "confidence": "high"},
        {"name": "밀폐 용기", "category": "기타", "confidence": "high"},
        {"name": "우유", "category": "이상한분류", "confidence": "??"},
        {"name": "  "},
    ], "notes": 3})
    names = [i["name"] for i in result["ingredients"]]
    check("중복 합치기 (확신도 높은 쪽 유지)", names.count("달걀") + names.count("달 걀") == 1
          and result["ingredients"][0]["confidence"] == "high" and result["ingredients"][0]["quantity"] == "6개",
          str(result["ingredients"][:1]))
    check("음식 아닌 물건 빼기", "밀폐 용기" not in names)
    check("모르는 분류/확신도 → 기타/medium",
          any(i["name"] == "우유" and i["category"] == "기타" and i["confidence"] == "medium"
              for i in result["ingredients"]))
    check("빈 이름 빼기, 잘못된 notes → 빈 문자열", len(names) == 2 and result["notes"] == "")
    suspect = {n: server.is_suspect_name(n, e) for n, e in [
        ("달/year", "egg"), ("메이onnaise", "mayonnaise"), ("파인플루트", "pineapple"), ("메추라 알", "quail eggs"),
        ("양상추", "lettuce"), ("계란", "eggs"), ("다진 마늘", "garlic"), ("페스토 / 그린 소스", "pesto"), ("두부", "")]}
    check("깨진 이름 → 확인 필요", all(suspect[n] for n in ("달/year", "메이onnaise", "파인플루트", "메추라 알")), str(suspect))
    check("정상 이름은 그대로", not any(suspect[n] for n in ("양상추", "계란", "다진 마늘", "페스토 / 그린 소스", "두부")),
          str(suspect))
    item = server.normalize({"ingredients": [{"name": "달/year", "name_en": "Egg", "category": "유제품/달걀",
                                              "confidence": "high"}]})["ingredients"][0]
    check("normalize가 name_en(소문자)과 name_suspect를 채움", item["name_en"] == "egg" and item["name_suspect"] is True)
    check("비슷한 분류 맞추기", [server.normalize_category(c) for c in ("유제품", "소스", "음료", None)]
          == ["유제품/달걀", "양념/소스", "음료", "기타"])

    print("[오류 처리 (가짜 모델 응답)]")
    original = server.chat_events
    good = json.dumps({"ingredients": [{"name": "당근", "quantity": "2개", "category": "채소",
                                         "confidence": "high"}], "notes": ""}, ensure_ascii=False)
    try:
        server.chat_events, calls = fake_chat("JSON이 아닌 답", good)
        server._cache.clear()
        status, events = post(image_bytes(size=(10, 10)))
        check("형식 틀리면 1번 더 요청 후 성공", events[-1]["type"] == "result" and len(calls) == 2
              and events[-1]["ingredients"][0]["name"] == "당근", str(events))

        server.chat_events, calls = fake_chat()
        status, events = post(image_bytes(size=(10, 10)))
        check("같은 사진은 캐시에서 (모델 호출 0회)", events[-1].get("cached") is True and not calls)

        server.chat_events, calls = fake_chat("틀림", "또 틀림")
        status, events = post(image_bytes(size=(11, 11)))
        check("2번 다 틀리면 parse_failed", events[-1].get("code") == "parse_failed" and len(calls) == 2)

        server.chat_events, _ = fake_chat(OpenRouterError("rate_limited", "HTTP 429"))
        status, events = post(image_bytes(size=(12, 12)))
        check("429 계속 → rate_limited, 서버는 200으로 응답 유지",
              status == 200 and events[-1].get("code") == "rate_limited")
        check("오류 메시지에 OpenRouter 원문 없음", "HTTP 429" not in json.dumps(events, ensure_ascii=False))

        server.chat_events, calls = fake_chat(OpenRouterError("empty", "빈 응답", "length"), good)
        status, events = post(image_bytes(size=(14, 14)))
        check("빈 응답(추론에 토큰 소진) → 한도 늘려 1번 더", events[-1]["type"] == "result"
              and calls == list(server.MAX_TOKENS), str(calls))

        server.chat_events, _ = fake_chat(OpenRouterError("upstream_error", "HTTP 500: secret detail"))
        status, events = post(image_bytes(size=(13, 13)))
        check("그 밖의 오류 → upstream_error", events[-1].get("code") == "upstream_error")
    finally:
        server.chat_events = original
        server._cache.clear()


def resize_like_browser(path):
    """브라우저(app.js)처럼 긴 변 1280px, JPEG 품질 85로 줄임."""
    image = Image.open(path).convert("RGB")
    image.thumbnail((1280, 1280))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def live_tests():
    print(f"[실제 모델: {server.IMAGE_MODEL}]")
    for path in sorted(SAMPLES.glob("*.jpg")):
        status, events = post(resize_like_browser(path), path.name)
        for event in events:
            if event["type"] == "retry":
                print(f"    {path.name}: {event['code']} 재시도 {event['attempt']}/{event['max']} ({event['wait']}초)")
        last = events[-1]
        if last["type"] != "result":
            check(f"{path.name} 인식", False, f"{last.get('code')}: {last.get('error')}")
            continue
        check(f"{path.name} 인식 ({len(last['ingredients'])}개, {last['elapsed_sec']}초)", bool(last["ingredients"]))
        for item in last["ingredients"]:
            print(f"      - {item['name']} {item['quantity']} [{item['category']}, {item['confidence']}]")
        if last["notes"]:
            print(f"      메모: {last['notes']}")


if __name__ == "__main__":
    offline_tests()
    if "--live" in sys.argv:
        live_tests()
    print(f"\n{'모두 통과' if not failures else f'실패 {len(failures)}건: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)
