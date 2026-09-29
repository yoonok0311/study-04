# Created: 2026-09-29 11:59
"""냉장고 레시피 추천 웹 앱 서버 (PRD_step1.md 재료 인식, PRD_step2.md 레시피 생성).

실행: py app.py  →  http://127.0.0.1:5000
브라우저는 OpenRouter를 직접 부르지 않고 이 서버의 /api/...만 부름. API 키는 서버에만 있음.
"""
import base64
import hashlib
import io
import json
import os
import re
import time
from collections import OrderedDict

from flask import Flask, Response, jsonify, request, send_from_directory
from PIL import Image, UnidentifiedImageError

import recipes
from ingredients import PROMPT, normalize
from openrouter import RETRY_WAITS, OpenRouterError, chat_events, extract_json

# 재료 인식 모델을 앞에서부터 시도 (쉼표로 구분). PRD 기본은 gemma지만 무료 공용 한도(429)가 잦아 dots-3를 대체로 둠
IMAGE_MODELS = [m.strip() for m in (os.environ.get("IMAGE_MODELS") or os.environ.get("IMAGE_MODEL") or
                "google/gemma-4-31b-it:free,dots-studio/dots-3-note-preview:free").split(",") if m.strip()]
# 레시피 생성 모델 (PRD 기본 dots-3, 막히면 텍스트 모델 nemotron)
RECIPE_MODELS = [m.strip() for m in (os.environ.get("RECIPE_MODELS") or os.environ.get("RECIPE_MODEL") or
                 "dots-studio/dots-3-note-preview:free,nvidia/nemotron-3-super-120b-a12b:free").split(",") if m.strip()]
FALLBACK_WAITS = (5,)  # 다음 모델이 있으면 한 번만 짧게 재시도하고 넘어감
RECIPE_CALLS = 4  # 레시피 요청 1번에 모델을 부르는 최대 횟수 (429 재시도 제외)
# dots-3는 추론을 켜 두면 레시피에 100초 넘게 추론만 하다 빈 응답을 냄 (추론 7,000토큰+).
# 끄면 약 20초에 레시피 3개를 냄. 추론을 지원하지 않는 모델은 이 필드를 무시함
RECIPE_EXTRA = {"reasoning": {"enabled": False}}
RECIPE_CACHE_SECONDS = 30 * 60
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 브라우저가 줄여서 보낸 뒤 기준
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
CACHE_SIZE = 100
# 추론 모델(dots-3 등)은 추론 토큰도 max_tokens에 포함됨: 처음 한도, 빈 응답일 때 늘린 한도
MAX_TOKENS = (8000, 16000)
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_BYTES + 64 * 1024  # multipart 여유분
_cache = OrderedDict()  # 이미지 sha256 → 결과 (같은 사진 재인식 시 무료 호출 한도 아끼기)
_recipe_cache = OrderedDict()  # 요청 sha256 → (저장 시각, 결과). 같은 재료와 조건이면 30분간 재사용


ERROR_MESSAGES = {
    "rate_limited": "사용자가 많아 인식하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
    "upstream_error": "AI 서비스에서 오류가 났습니다. 잠시 뒤 다시 시도해 주세요.",
    "parse_failed": "AI 응답을 해석하지 못했습니다. 다시 시도해 주세요.",
    "no_match": "조건에 맞는 레시피를 찾지 못했습니다. 피할 재료나 '가진 재료만 사용' 조건을 바꿔 보세요.",
}


def error_body(code, message):
    return {"type": "error", "code": code, "error": message}


def recognize_with(model, content, waits):
    """모델 하나로 인식. 진행 이벤트를 내보내고 (결과 dict 또는 None, 오류 code)를 돌려줌.
    형식이 틀린 응답은 1번 더 요청 (F1-9), 빈 응답이면 max_tokens를 늘려 1번 더."""
    max_tokens = MAX_TOKENS[0]
    for attempt in range(2):
        try:
            for kind, info in chat_events(model, content, max_tokens=max_tokens, waits=waits):
                if kind == "retry":
                    yield {"type": "retry", **info}
                else:
                    reply = info["content"]
        except OpenRouterError as e:
            app.logger.warning("%s 실패 (%s, finish_reason=%s): %s", model, e.kind, e.finish_reason, e)
            if e.kind == "empty" and attempt == 0:
                max_tokens = MAX_TOKENS[1]
                yield {"type": "status", "message": "AI가 답을 끝맺지 못해 다시 요청하는 중…"}
                continue
            return None, "rate_limited" if e.kind == "rate_limited" else "upstream_error"
        try:
            return normalize(extract_json(reply)), None
        except ValueError as e:  # json.JSONDecodeError도 ValueError
            app.logger.warning("%s 응답 형식 오류 (%d번째): %s / %.200s", model, attempt + 1, e, reply)
            if attempt == 0:
                yield {"type": "status", "message": "응답 형식이 맞지 않아 다시 요청하는 중…"}
    return None, "parse_failed"


def recognize_events(data_url):
    """IMAGE_MODELS를 앞에서부터 시도. 앞 모델은 짧게 재시도하고 실패하면 다음 모델로 넘어감."""
    start = time.perf_counter()
    content = [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": data_url}}]
    for index, model in enumerate(IMAGE_MODELS):
        is_last = index == len(IMAGE_MODELS) - 1
        result, code = yield from recognize_with(model, content, RETRY_WAITS if is_last else FALLBACK_WAITS)
        if result is not None:
            yield {"type": "result", **result, "model": model, "elapsed_sec": round(time.perf_counter() - start, 1)}
            return
        if not is_last:
            yield {"type": "status", "message": f"{short_name(model)} 모델이 응답하지 않아 "
                                                f"{short_name(IMAGE_MODELS[index + 1])} 모델로 바꿔 시도하는 중…"}
    yield error_body(code, ERROR_MESSAGES[code])


def short_name(model):
    return model.split("/")[-1].replace(":free", "")


def ndjson_response(events):
    """재시도가 길어질 수 있어(최대 약 3분) 진행 상황을 한 줄에 JSON 하나씩 흘려보냄."""
    lines = (json.dumps(event, ensure_ascii=False) + "\n" for event in events)
    return Response(lines, mimetype="application/x-ndjson", headers={"Cache-Control": "no-store"})


def recipe_events(req):
    """레시피 생성 진행 상황을 NDJSON 줄로 내보냄 (PRD_step2.md 4.2).

    조건(피할 재료, 가진 재료만, 중복)에 어긋난 레시피는 버리고 모자란 수만큼 다시 요청 (F2-8, F2-10).
    빈 응답이면 max_tokens를 늘려 다시 (F2-7), 모델이 막히면 다음 모델로.
    """
    start = time.perf_counter()
    owned = recipes.owned_names(req)
    accepted, taken = [], list(req["exclude_titles"])
    model_index, max_tokens, code, used_model = 0, MAX_TOKENS[0], "no_match", None
    for _ in range(RECIPE_CALLS):
        model = RECIPE_MODELS[model_index]
        is_last = model_index == len(RECIPE_MODELS) - 1
        need = req["count"] - len(accepted)
        prompt = recipes.build_prompt(req, need, taken)
        try:
            for kind, info in chat_events(model, prompt, max_tokens=max_tokens, extra=RECIPE_EXTRA,
                                          waits=RETRY_WAITS if is_last else FALLBACK_WAITS):
                if kind == "retry":
                    yield {"type": "retry", **info}
                else:
                    reply = info["content"]
        except OpenRouterError as e:
            app.logger.warning("%s 실패 (%s, finish_reason=%s): %s", model, e.kind, e.finish_reason, e)
            if e.kind == "empty" and max_tokens == MAX_TOKENS[0]:
                max_tokens = MAX_TOKENS[1]
                yield {"type": "status", "message": "AI가 답을 끝맺지 못해 다시 요청하는 중…"}
                continue
            if not is_last:
                model_index, max_tokens = model_index + 1, MAX_TOKENS[0]
                yield {"type": "status", "message": f"{short_name(model)} 모델이 응답하지 않아 "
                                                    f"{short_name(RECIPE_MODELS[model_index])} 모델로 바꿔 시도하는 중…"}
                continue
            code = "rate_limited" if e.kind == "rate_limited" else "upstream_error"
            break
        try:
            candidates = recipes.parse_recipes(extract_json(reply), req["options"]["servings"])
        except ValueError as e:
            app.logger.warning("%s 레시피 형식 오류: %s / %.200s", model, e, reply)
            code = "parse_failed"
            yield {"type": "status", "message": "응답 형식이 맞지 않아 다시 요청하는 중…"}
            continue
        used_model = model
        for recipe in candidates:
            recipes.annotate(recipe, owned)
            reason = recipes.rejection_reason(recipe, req, taken)
            if reason:
                app.logger.info("레시피 제외 (%s): %s", reason, recipe["title"])
                continue
            accepted.append(recipe)
            taken.append(recipe["title"])
            if len(accepted) >= req["count"]:
                break
        if len(accepted) >= req["count"]:
            break
        code = "no_match"
        yield {"type": "status",
               "message": f"조건에 맞는 레시피가 {len(accepted)}/{req['count']}개라 더 요청하는 중…"}

    if not accepted:
        yield error_body(code, ERROR_MESSAGES[code])
        return
    # 가진 재료 비율이 높은 순 (F2-13)
    accepted.sort(key=lambda r: r["have_count"] / max(1, r["total_count"]), reverse=True)
    note = "" if len(accepted) >= req["count"] else f"조건에 맞는 레시피를 {len(accepted)}개만 찾았습니다."
    yield {"type": "result", "recipes": accepted, "note": note, "model": used_model,
           "elapsed_sec": round(time.perf_counter() - start, 1)}


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    """화면이 서버를 찾을 때 씀 (index.html을 파일로 열거나 Live Server로 연 경우)."""
    return jsonify({"ok": True, "models": IMAGE_MODELS, "recipe_models": RECIPE_MODELS})


# index.html을 파일(file://)이나 다른 로컬 포트(VS Code Live Server 등)로 열어도 이 서버를 부를 수 있게 허용.
# 로컬 출처만 허용하므로 다른 사이트는 이 서버(와 API 키 사용량)를 쓸 수 없음
LOCAL_ORIGIN = re.compile(r"^(null|https?://(127\.0\.0\.1|localhost)(:\d+)?)$")


@app.after_request
def allow_local_origins(response):
    origin = request.headers.get("Origin", "")
    if LOCAL_ORIGIN.match(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


@app.post("/api/ingredients")
def ingredients():
    upload = request.files.get("image")
    if upload is None:
        return jsonify(error_body("bad_image", "이미지가 없습니다.")), 400
    raw = upload.read()
    if len(raw) > MAX_IMAGE_BYTES:
        return jsonify(error_body("bad_image", "이미지가 너무 큽니다 (최대 5MB).")), 400
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        image_format = None
    if image_format not in ALLOWED_FORMATS:
        return jsonify(error_body("bad_image", "JPG/PNG/WEBP 이미지로 올려 주세요.")), 400

    digest = hashlib.sha256(raw).hexdigest()
    data_url = f"data:{ALLOWED_FORMATS[image_format]};base64," + base64.b64encode(raw).decode("ascii")

    def stream():
        if digest in _cache:
            _cache.move_to_end(digest)
            yield {**_cache[digest], "cached": True}
            return
        for event in recognize_events(data_url):
            if event["type"] == "result":
                _cache[digest] = event
                while len(_cache) > CACHE_SIZE:
                    _cache.popitem(last=False)
            yield event

    return ndjson_response(stream())


@app.post("/api/recipes")
def recipes_api():
    try:
        req = recipes.parse_request(request.get_json(silent=True))
    except recipes.RequestError as e:
        return jsonify(error_body("bad_request", str(e))), 400
    digest = hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def stream():
        cached = _recipe_cache.get(digest)
        if cached and time.time() - cached[0] < RECIPE_CACHE_SECONDS:
            yield {**cached[1], "cached": True}
            return
        for event in recipe_events(req):
            if event["type"] == "result":
                _recipe_cache[digest] = (time.time(), event)
                while len(_recipe_cache) > CACHE_SIZE:
                    _recipe_cache.popitem(last=False)
            yield event

    return ndjson_response(stream())


@app.errorhandler(413)
def too_large(_):
    return jsonify(error_body("bad_image", "이미지가 너무 큽니다 (최대 5MB).")), 413


if __name__ == "__main__":
    print(f"재료 인식 모델 (순서대로 시도): {', '.join(IMAGE_MODELS)}")
    print(f"레시피 생성 모델 (순서대로 시도): {', '.join(RECIPE_MODELS)}")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), threaded=True)
