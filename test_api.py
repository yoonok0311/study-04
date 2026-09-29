# Created: 2026-09-29 11:04
"""OpenRouter API 동작 테스트: 텍스트 질문 1회, 이미지 글자 인식(OCR) 1회.

실행: py test_api.py [--text-model ID] [--image-model ID] [--only text|image]
테스트 이미지(test_image.png)는 Pillow로 매번 새로 그림. 호출과 재시도는 openrouter.py.
"""
import argparse
import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from openrouter import chat

TEXT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"  # 텍스트 전용 추론 모델
IMAGE_MODEL = "dots-studio/dots-3-note-preview:free"  # 이미지 글자 인식용
IMAGE_PATH = Path(__file__).resolve().parent / "test_image.png"
IMAGE_LINES = ["Hello OpenRouter 2026", "안녕하세요, 이미지 인식 테스트입니다.", "Total: 12,345원"]


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


def print_retry(info):
    print(f"  {info['code']} 일시적 오류, {info['wait']}초 후 재시도 ({info['attempt']}/{info['max']})")


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
            args.text_model, "대한민국의 수도는 어디인가요? 한 문장으로 답하세요.", max_tokens=2000,
            on_retry=print_retry))
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
        ], max_tokens=2000, on_retry=print_retry))
        found = [line for line in IMAGE_LINES if answer and line in answer]
        results.append(bool(found))
        summary.append(f"이미지: 원문 {len(IMAGE_LINES)}줄 중 {len(found)}줄 정확히 일치")

    print("=== 결과 ===")
    print("\n".join(summary))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
