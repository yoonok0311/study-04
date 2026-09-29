# Created: 2026-09-29 11:04
"""OpenRouter API 동작 테스트: 텍스트 질문 1회, 이미지 글자 인식(OCR) 1회.

실행: py test_api.py [--text-model ID] [--image-model ID] [--only text|image]
테스트 이미지(test_image.png)는 Pillow로 매번 새로 그림. 키는 config.py로만 불러옴.
"""
import argparse
import base64
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import OPENROUTER_BASE_URL, get_api_key

TEXT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"  # 텍스트 전용 추론 모델
IMAGE_MODEL = "dots-studio/dots-3-note-preview:free"  # 이미지 글자 인식용
IMAGE_PATH = Path(__file__).resolve().parent / "test_image.png"
IMAGE_LINES = ["Hello OpenRouter 2026", "안녕하세요, 이미지 인식 테스트입니다.", "Total: 12,345원"]


def chat(model, content, max_tokens=300, retries=4):
    body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens}
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {get_api_key()}", "Content-Type": "application/json"},
    )
    start = time.perf_counter()
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.load(response)
        except urllib.error.HTTPError as e:
            code, detail = e.code, e.read().decode("utf-8", "replace")[:300]
        else:
            # 제공사 오류는 HTTP 200 본문의 "error"로 오기도 함 (예: 503 과부하)
            if "error" not in data:
                break
            code, detail = data["error"].get("code"), data["error"]
        # 무료 모델은 공용 한도(429)나 과부하(502/503)가 잦음: 10, 20, 40, 80초 기다렸다 재시도
        if code in (429, 502, 503) and attempt < retries:
            wait = 10 * 2 ** attempt
            print(f"  {code} 일시적 오류, {wait}초 후 재시도 ({attempt + 1}/{retries})")
            time.sleep(wait)
            continue
        raise RuntimeError(f"HTTP {code}: {detail}")
    elapsed = time.perf_counter() - start
    # 추론 모델은 max_tokens를 추론에 다 써 버리면 content가 비어서 옴
    content = (data["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError(f"빈 응답 (finish_reason={data['choices'][0].get('finish_reason')})")
    return content, data.get("usage", {}), elapsed


def make_test_image():
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 36)
    image = Image.new("RGB", (760, 220), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(IMAGE_LINES):
        draw.text((30, 25 + i * 60), line, fill="black", font=font)
    image.save(IMAGE_PATH)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def report(title, run):
    print(f"=== {title} ===")
    try:
        answer, usage, elapsed = run()
    except Exception as e:
        print(f"실패: {e}\n")
        return None
    print(answer)
    print(f"-- {elapsed:.1f}초, 토큰 {usage.get('prompt_tokens')}+{usage.get('completion_tokens')}\n")
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-model", default=TEXT_MODEL)
    parser.add_argument("--image-model", default=IMAGE_MODEL)
    parser.add_argument("--only", choices=["text", "image"])
    args = parser.parse_args()
    results = []

    if args.only != "image":
        # 추론 토큰까지 max_tokens에 포함되므로 넉넉히 줌
        answer = report(f"텍스트 테스트 ({args.text_model})", lambda: chat(
            args.text_model, "대한민국의 수도는 어디인가요? 한 문장으로 답하세요.", max_tokens=2000))
        ok = bool(answer) and "서울" in answer
        results.append(ok)
        summary = [f"텍스트: {'성공' if ok else '실패'}"]
    else:
        summary = []

    if args.only != "text":
        image_url = make_test_image()
        answer = report(f"이미지 인식 테스트 ({args.image_model})", lambda: chat(args.image_model, [
            {"type": "text", "text": "이 이미지에 적힌 글자를 줄 단위로 그대로 옮겨 적으세요. 다른 설명은 하지 마세요."},
            {"type": "image_url", "image_url": {"url": image_url}},
        ], max_tokens=2000))
        found = [line for line in IMAGE_LINES if answer and line in answer]
        results.append(bool(found))
        summary.append(f"이미지: 원문 {len(IMAGE_LINES)}줄 중 {len(found)}줄 정확히 일치")

    print("=== 결과 ===")
    print("\n".join(summary))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
