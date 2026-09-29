# CLAUDE.md

이 파일은 이 저장소에서 코드를 다룰 때 Claude Code(claude.ai/code)가 참고할 지침입니다.

<!-- Created: 2026-09-29 10:57 -->

## 프로젝트 개요

VibeCoding 학습 시리즈의 Study-04입니다 (다른 프로젝트: `../study-01` MNIST 숫자 인식기, `../study-02` 웹 할 일 앱, `../study-03` 한국어 퀴즈 웹 게임). 냉장고 사진에서 재료를 인식하고 레시피를 추천하는 웹 앱을 `PRD_step1.md`(재료 인식), `PRD_step2.md`(레시피 생성), `PRD_step3.md`(프로필과 저장) 순서로 만들고 있습니다. 현재 1단계까지 구현되어 있습니다.

## 실행과 테스트

- `py app.py`: Flask 서버를 `http://127.0.0.1:5000`에 띄웁니다 (의존성: `flask`, `Pillow`). 모델은 환경 변수 `IMAGE_MODEL`, 포트는 `PORT`로 바꿉니다. 예: `PORT=5001 IMAGE_MODEL=dots-studio/dots-3-note-preview:free py app.py`. 자동 재시작이 없으므로 코드를 고치면 서버를 다시 켭니다.
- `py test_step1.py`: API를 부르지 않는 서버 테스트 (가짜 `chat_events`로 오류 흐름 검사). `--live`를 붙이면 `samples/`의 사진 3장으로 실제 모델을 부릅니다 (무료 호출 한도 사용).
- 콘솔 한글이 깨지면 `PYTHONIOENCODING=utf-8`을 붙입니다.

## 구조

- `openrouter.py`: 모든 OpenRouter 호출의 공통 모듈. `chat_events()`는 재시도 진행을 `("retry", …)` 이벤트로 내보내는 제너레이터이고, `chat()`은 이를 끝까지 돌리는 래퍼입니다. 재시도를 다 써도 실패하면 `OpenRouterError(kind=rate_limited|upstream_error|empty)`를 냅니다. `extract_json()`은 코드 블록이나 앞뒤 설명이 붙은 응답에서 JSON을 뽑습니다.
- `app.py`: `POST /api/ingredients`는 결과를 한 번에 주지 않고 NDJSON(`application/x-ndjson`)으로 흘려보냅니다. `retry`/`status` 줄이 0개 이상 오고 마지막 줄이 `result` 또는 `error`입니다. 재시도가 최대 약 3분 걸려서 화면에 진행 상황을 보여 주기 위함입니다. 업로드 검증 실패만 일반 JSON 400으로 돌려줍니다. 인식 결과는 이미지 sha256으로 메모리에 캐시합니다.
- 모델 응답은 `normalize()`로 정리합니다: 중복 합치기, 음식 아닌 물건 빼기, 목록에 없는 분류는 `normalize_category()`로 비슷한 분류에 맞추기. dots-3가 한글 이름을 자주 깨뜨려서(예: `달/year`, `파인플루트`) 영어 이름 `name_en`도 받고, `is_suspect_name()`이 한글 외 문자가 섞였거나 `KNOWN_NAMES`의 영어→한글 대응과 어긋나면 `name_suspect: true`를 붙입니다. 화면은 이를 "확인 필요"와 영어 이름 힌트로 보여 주고, 사용자가 이름을 고치면 표시를 지웁니다. 형식이 틀리거나 빈 응답이면 1번 더 요청합니다 (빈 응답이면 `MAX_TOKENS`를 늘려서).
- `static/`: 빌드 없는 HTML/CSS/JS. `app.js`가 보내기 전에 사진을 긴 변 1280px JPEG로 줄이고, 편집한 재료 목록을 `sessionStorage`(`fridge.step1`)에 둡니다. 2단계는 이 목록을 받아 씁니다. 원본 사진은 메모리에만 있어서 새로 고침하면 다시 인식할 수 없습니다.
- `samples/`: 테스트 사진과 출처, 눈으로 센 정답 재료 목록(`SOURCES.md`).

`study-04/`가 git 저장소 루트입니다 (기본 브랜치 `main`, 원격 `origin` = https://github.com/yoonok0311/study-04, 비공개). 사용자가 명시적으로 요청할 때만 커밋합니다. 린터와 빌드 단계는 없습니다. 공통 규칙(생성 시각 주석, `py` 런처)은 `C:\Users\DY\Desktop\CLAUDE.md`를 따릅니다.

## 비밀 정보

- `.env`에 OpenRouter 키 `OPENROUTER_API_KEY`가 있습니다. 키는 항상 `config.py`의 `get_api_key()`로 불러옵니다 (표준 라이브러리만 사용, `python-dotenv` 미설치). 코드에 직접 적거나, 출력하거나, 브라우저로 전달되는 클라이언트 코드에 넣지 않습니다. 로그에는 `mask(key)`를 씁니다.
- API 기본 주소는 `config.OPENROUTER_BASE_URL` (`https://openrouter.ai/api/v1`)이고 인증은 `Authorization: Bearer <키>` 헤더입니다.
- `py config.py`: 키를 출력하지 않고 OpenRouter에 키가 유효한지, 사용액과 한도를 확인합니다.
- 모델: `app.py`의 재료 인식 기본값은 PRD대로 `google/gemma-4-31b-it:free`이지만, 이 모델은 2026-09-29 내내 공용 한도 429로 한 번도 응답하지 않았습니다. 실제로 동작을 확인한 것은 `dots-studio/dots-3-note-preview:free`(재료 인식, 사진당 50~100초)와 `nvidia/nemotron-3-super-120b-a12b:free`(텍스트)입니다. 둘 다 추론 모델이라 추론 토큰도 `max_tokens`에 포함됩니다. dots-3 재료 인식은 3000으로는 매번 빈 응답(`finish_reason=length`)이어서 `MAX_TOKENS`가 8000으로 시작합니다. `test_api.py`는 간단한 확인용이라 2000을 씁니다.
- `py test_api.py [--text-model ID] [--image-model ID] [--only text|image]`: 텍스트 질문과 이미지 글자 인식을 한 번씩 테스트합니다. 테스트 이미지 `test_image.png`는 매번 Pillow로 새로 그립니다. 무료 모델은 공용 한도(429)나 과부하(502/503)가 잦아서 10/20/40/80초 간격으로 재시도합니다. 제공사 오류는 HTTP 200 응답 본문의 `error`로 오기도 합니다. 이 키는 무료 등급이라 무료 모델을 하루 50회까지 호출할 수 있습니다.
- `.githooks/pre-commit`이 `.env` 파일, `sk-or-v1-…` 형식 문자열, `.env`의 실제 키 값이 커밋에 들어가면 커밋을 막습니다. 훅은 clone으로 켜지지 않으므로 새로 clone하면 `git config core.hooksPath .githooks`를 실행합니다. `--no-verify`로 우회하지 않습니다.
- 키 값을 화면이나 로그에 출력하지 않습니다. 확인이 필요하면 `mask(key)`나 길이, 접두사만 봅니다.
- `.gitignore`가 `.env`를 제외합니다. 커밋하는 것은 자리표시자만 든 `.env.example`입니다.

## 환경

- Python 3.9.7은 `py`로 실행합니다. Node v16.13.2도 설치되어 있습니다.
