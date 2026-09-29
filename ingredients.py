# Created: 2026-09-29 12:57
"""1단계: 모델이 준 재료 인식 결과를 검증하고 정리 (PRD_step1.md). 프롬프트, 분류 맞추기, 깨진 이름 판별.

Flask와 무관한 순수 함수만 둠. 모델 호출 흐름은 app.py의 recognize_events.
"""
import re
from collections import OrderedDict

CATEGORIES = ["채소", "과일", "육류", "해산물", "유제품/달걀", "가공식품", "양념/소스", "음료", "기타"]
CONFIDENCES = ("high", "medium", "low")
# 모델이 가끔 재료처럼 적는 음식 아닌 물건 (F1-10)
NON_FOOD = {"용기", "밀폐용기", "반찬통", "플라스틱용기", "유리병", "비닐", "비닐봉지", "봉지", "랩",
            "쟁반", "그릇", "접시", "선반", "냉장고", "칸막이", "지퍼백", "호일", "알루미늄호일"}
# 한글 이름에 허용하는 글자: 한글, 숫자, 공백, 몇 가지 기호. 영어가 섞이면(예: "달/year") 깨진 이름으로 봄
VALID_NAME = re.compile(r"^[가-힣0-9 ()·,/&-]+$")
# 영어 이름 → 맞는 한글 이름들. 영어는 맞는데 한글이 다르면(예: pineapple인데 "파인플루트") 깨진 이름으로 봄.
# 한글 이름이 이 중 하나를 포함하거나 그 반대면 맞는 것으로 봄 ("양상추" ⊃ "상추")
KNOWN_NAMES = {
    "egg": ["달걀", "계란"], "eggs": ["달걀", "계란"], "quail egg": ["메추리알"], "quail eggs": ["메추리알"],
    "milk": ["우유"], "butter": ["버터"], "cheese": ["치즈"], "yogurt": ["요거트", "요구르트"],
    "mayonnaise": ["마요네즈"], "ketchup": ["케첩", "케찹"], "mustard": ["머스터드", "겨자"],
    "soy sauce": ["간장"], "pineapple": ["파인애플"], "apple": ["사과"], "banana": ["바나나"],
    "orange": ["오렌지"], "tangerine": ["귤"], "mandarin": ["귤"], "lemon": ["레몬"], "grape": ["포도"],
    "strawberry": ["딸기"], "watermelon": ["수박"], "carrot": ["당근"], "cabbage": ["양배추", "배추"],
    "lettuce": ["상추"], "cucumber": ["오이"], "tomato": ["토마토"], "onion": ["양파"],
    "garlic": ["마늘"], "green onion": ["파"], "scallion": ["파"], "potato": ["감자"],
    "sweet potato": ["고구마"], "broccoli": ["브로콜리"], "spinach": ["시금치"], "mushroom": ["버섯"],
    "zucchini": ["애호박", "주키니"], "pepper": ["고추", "피망", "파프리카"], "tofu": ["두부"],
    "kimchi": ["김치"], "bread": ["빵"], "ham": ["햄"], "sausage": ["소시지"], "bacon": ["베이컨"],
    "chicken": ["닭"], "pork": ["돼지"], "beef": ["소고기", "쇠고기"], "fish": ["생선"], "shrimp": ["새우"],
    "juice": ["주스"], "water": ["물"], "beer": ["맥주"], "cola": ["콜라"],
}

PROMPT = f"""당신은 냉장고 사진에서 식재료를 찾아내는 도우미입니다.
사진에 보이는 식재료를 모두 찾아 아래 JSON 형식으로만 답하세요. JSON 밖에는 아무것도 쓰지 마세요.

{{
  "ingredients": [
    {{"name": "달걀", "name_en": "egg", "quantity": "6개", "category": "유제품/달걀", "confidence": "high"}}
  ],
  "notes": "사진 상태에 대한 짧은 메모 (없으면 빈 문자열)"
}}

규칙:
- name: 한국어 일반 명칭 (상표명 말고 "우유", "케첩"처럼). 영어를 섞지 말고 한글로만. 같은 재료는 한 번만 적기.
- name_en: 같은 재료의 영어 일반 명칭, 소문자 단수형 (예: "egg", "soy sauce").
- quantity: 대략적인 양 (예: "3개", "1/2통", "약 300g"). 알아볼 수 없으면 "".
- category: {", ".join(CATEGORIES)} 중 하나.
- confidence: 확실하면 "high", 아마 맞으면 "medium", 잘 안 보여 추측이면 "low".
- 용기, 비닐, 선반 같은 음식이 아닌 물건은 적지 마세요.
- 식재료가 하나도 보이지 않으면 "ingredients"를 빈 배열로 두세요."""


# dots-3는 "달걀"의 "걀"을 거의 매번 영어로 깨뜨림 (예: "달/year", "달 Goose", "달_eggs_", "달ayne")
BROKEN_EGG = re.compile(r"달[\s_/]*[A-Za-z]+(?:[\s_]+[A-Za-z]+)*_*")


def repair_korean(text):
    """알려진 깨짐 패턴을 고침. 지금은 달걀뿐."""
    return BROKEN_EGG.sub("달걀", text)


def normalize_category(value):
    """목록에 없는 분류는 비슷한 분류로 맞춤 (예: "유제품" → "유제품/달걀", "소스" → "양념/소스")."""
    value = str(value or "").strip()
    if value in CATEGORIES:
        return value
    for category in CATEGORIES:
        if any(part in value for part in category.split("/")):
            return category
    return "기타"


def is_suspect_name(name, name_en):
    """모델이 한글 이름을 깨뜨렸는지 (예: "달/year", "메이onnaise", pineapple인데 "파인플루트")."""
    if not VALID_NAME.match(name):
        return True
    known = KNOWN_NAMES.get(name_en) or KNOWN_NAMES.get(name_en.rstrip("s"))
    if known:
        compact = name.replace(" ", "")
        return not any(k in compact or compact in k for k in known)
    return False


def normalize(data):
    """모델 JSON을 검증하고 정리. 형식이 틀리면 ValueError."""
    items = data.get("ingredients") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("ingredients 배열이 없습니다.")
    merged = OrderedDict()
    for item in items:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        name = repair_korean(str(item["name"]).strip())[:30]
        key = name.replace(" ", "")
        if key in NON_FOOD:
            continue
        confidence = item.get("confidence") if item.get("confidence") in CONFIDENCES else "medium"
        name_en = str(item.get("name_en") or "").strip().lower()[:40]
        entry = {
            "name": name,
            "name_en": name_en,
            "name_suspect": is_suspect_name(name, name_en),  # 화면에서 "확인 필요"로 표시
            "quantity": str(item.get("quantity") or "").strip()[:30],
            "category": normalize_category(item.get("category")),
            "confidence": confidence,
        }
        if key in merged:  # 중복이면 확신도가 높은 쪽을 남기고, 비어 있는 양은 채움
            old = merged[key]
            if CONFIDENCES.index(confidence) < CONFIDENCES.index(old["confidence"]):
                entry["quantity"] = entry["quantity"] or old["quantity"]
                merged[key] = entry
            elif not old["quantity"]:
                old["quantity"] = entry["quantity"]
        else:
            merged[key] = entry
    notes = data.get("notes")
    notes = repair_korean(notes.strip())[:300] if isinstance(notes, str) else ""
    return {"ingredients": list(merged.values()), "notes": notes}
