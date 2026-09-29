# Created: 2026-09-29 11:00
"""OpenRouter API 키를 .env에서 불러오는 모듈 (표준 라이브러리만 사용).

사용법:
    from config import get_api_key
    headers = {"Authorization": f"Bearer {get_api_key()}"}

키 확인:
    py config.py   # 키를 화면에 출력하지 않고 OpenRouter에 유효한지만 물어봄
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"
KEY_NAME = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def load_env(path=ENV_PATH):
    """KEY=VALUE 형식의 .env를 읽어 os.environ에 넣음. 이미 설정된 환경 변수는 덮어쓰지 않음."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def get_api_key():
    load_env()
    key = os.environ.get(KEY_NAME, "")
    if not key:
        raise RuntimeError(f"{KEY_NAME}가 없습니다. .env.example을 .env로 복사하고 키를 넣으세요.")
    return key


def mask(key):
    """로그에 남길 때 쓰는 가린 형태 (예: sk-or-v1-…a1b2)."""
    return f"{key[:9]}…{key[-4:]}" if len(key) > 13 else "***"


if __name__ == "__main__":
    key = get_api_key()
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/key", headers={"Authorization": f"Bearer {key}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response).get("data", {})
    except urllib.error.HTTPError as e:
        print(f"키 확인 실패 ({mask(key)}): HTTP {e.code}")
        raise SystemExit(1)
    print(f"키 정상 ({mask(key)})")
    print(f"  사용액: {data.get('usage')}  한도: {data.get('limit')}  무료 등급: {data.get('is_free_tier')}")
