<!-- Created: 2026-09-29 11:55 -->
# PRD 3단계: 사용자 프로필과 레시피 저장

## 1. 개요

사용자 계정과 프로필을 만들고, 2단계에서 추천받은 레시피를 저장해 나중에 다시 볼 수 있게 한다. 프로필의 알레르기와 식습관 정보는 레시피를 추천할 때 자동으로 반영한다. 1, 2단계가 끝나 있어야 한다 (`PRD_step1.md`, `PRD_step2.md`).

## 2. 목표와 범위

### 목표
- 사용자가 가입하고 로그인해서 자기 레시피 보관함을 가진다.
- 프로필에 적은 알레르기와 싫어하는 재료가 레시피 추천에 항상 반영된다.
- 저장한 레시피를 찾고, 메모와 평점을 남기고, 지울 수 있다.

### 범위에 포함
- 회원 가입, 로그인, 로그아웃 (아이디와 비밀번호)
- 프로필 입력과 수정
- 레시피 저장, 보관함 목록, 상세, 삭제, 메모와 평점
- 로그인하지 않은 사용자도 1, 2단계는 그대로 쓸 수 있음

### 범위에서 제외
- 소셜 로그인, 이메일 인증, 비밀번호 찾기
- 다른 사용자와 레시피 공유
- 여러 서버에 배포 (이 PC의 로컬 서버 기준)
- 사진 저장 (냉장고 사진은 계속 저장하지 않는다)

## 3. 사용자 시나리오

1. 사용자가 상단의 "로그인"에서 가입한다 (아이디, 비밀번호, 이름).
2. 가입 직후 프로필 화면에서 알레르기(예: 땅콩, 새우), 식습관(예: 채식), 싫어하는 재료, 요리 실력, 기본 인분을 적는다. 모두 선택 사항이다.
3. 1, 2단계를 거쳐 레시피를 추천받는다. 조건 입력 화면에 프로필 값이 미리 채워져 있고, 알레르기는 "프로필에서 가져옴"으로 표시된다.
4. 레시피 상세 화면에서 "저장"을 누른다. 로그인하지 않았으면 로그인 화면으로 갔다가 돌아와서 저장된다.
5. "내 레시피"에서 저장한 레시피를 최신순으로 본다. 이름으로 검색하거나 요리 종류로 거를 수 있다.
6. 직접 만들어 본 뒤 별점(1~5)과 메모("간장 반만 넣을 것")를 남긴다. 필요 없는 레시피는 지운다.

## 4. 기능 요구사항

### 4.1 계정
| ID | 요구사항 |
|---|---|
| F3-1 | 가입: 아이디(영문 소문자, 숫자, `_`로 4~20자, 중복 불가), 비밀번호(8자 이상), 이름(1~20자). |
| F3-2 | 비밀번호는 `hashlib.pbkdf2_hmac`(SHA-256, 반복 200,000회, 사용자마다 다른 salt)로 해시해서 저장한다. 원문은 어디에도 저장하거나 기록하지 않는다. |
| F3-3 | 로그인하면 Flask 세션 쿠키(`HttpOnly`, `SameSite=Lax`)를 발급한다. 세션 비밀 값은 `.env`의 `FLASK_SECRET_KEY`에서 읽고, 없으면 서버가 시작하지 않는다. |
| F3-4 | 로그인에 5번 연속 실패하면 그 아이디는 5분간 로그인을 막는다. |
| F3-5 | 로그아웃하면 세션을 지운다. |
| F3-6 | 회원 탈퇴를 하면 프로필과 저장한 레시피를 모두 지운다. 비밀번호를 한 번 더 확인한다. |

### 4.2 프로필
| ID | 요구사항 |
|---|---|
| F3-7 | 항목: 이름, 알레르기(목록), 식습관(없음/채식/비건/페스코/할랄 중 하나), 싫어하는 재료(목록), 요리 실력(초보/보통/능숙), 기본 인분(1~6). |
| F3-8 | 추천 조건 화면(2단계)을 열 때 로그인 상태면 프로필 값으로 기본값을 채운다. 사용자는 이번 추천에서만 값을 바꿀 수 있다. |
| F3-9 | 알레르기와 싫어하는 재료는 2단계의 "피할 재료"에 항상 합쳐서 보낸다. 알레르기는 화면에서 끌 수 없게 한다. |
| F3-10 | 식습관과 요리 실력은 레시피 생성 프롬프트에 조건으로 넣는다 (요리 실력 초보면 난이도 "쉬움" 위주). |

### 4.3 레시피 저장
| ID | 요구사항 |
|---|---|
| F3-11 | 저장할 때 레시피 JSON 전체(2단계 형식), 추천에 쓴 재료 목록, 사용한 모델 ID, 저장 시각을 함께 저장한다. 저장한 레시피는 AI를 다시 부르지 않고 보여 준다. |
| F3-12 | 같은 사용자가 같은 이름과 같은 재료 구성의 레시피를 또 저장하면 "이미 저장한 레시피입니다"로 막는다. |
| F3-13 | 보관함은 최신순으로 20개씩 보여 준다. 이름 검색, 요리 종류 필터, 평점순 정렬을 지원한다. |
| F3-14 | 저장한 레시피에 별점(1~5)과 메모(500자까지)를 달고 고칠 수 있다. 레시피 본문은 고치지 않는다. |
| F3-15 | 한 사용자당 레시피는 500개까지 저장할 수 있다. |
| F3-16 | 저장한 레시피를 볼 때 현재 프로필의 알레르기 재료가 들어 있으면 경고를 보여 준다 (프로필을 나중에 바꾼 경우 대비). |

### 4.4 API
모든 API는 로그인이 필요하며 (가입, 로그인 제외) 자기 데이터만 읽고 쓸 수 있다. 다른 사용자의 레시피 ID로 요청하면 404를 돌려준다.

| 메서드와 경로 | 설명 |
|---|---|
| `POST /api/auth/signup` | 가입 |
| `POST /api/auth/login` / `POST /api/auth/logout` | 로그인, 로그아웃 |
| `GET /api/me` / `PUT /api/me` / `DELETE /api/me` | 프로필 조회, 수정, 탈퇴 |
| `GET /api/saved-recipes?q=&cuisine=&sort=&page=` | 보관함 목록 |
| `POST /api/saved-recipes` | 레시피 저장 |
| `GET /api/saved-recipes/<id>` | 저장한 레시피 상세 |
| `PATCH /api/saved-recipes/<id>` | 별점, 메모 수정 |
| `DELETE /api/saved-recipes/<id>` | 삭제 |

## 5. 데이터 모델 (SQLite, `data/app.db`)

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,          -- pbkdf2 결과 (hex)
    password_salt TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE profiles (
    user_id              INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    allergies            TEXT NOT NULL DEFAULT '[]',   -- JSON 배열
    diet                 TEXT NOT NULL DEFAULT '없음',
    disliked_ingredients TEXT NOT NULL DEFAULT '[]',   -- JSON 배열
    skill_level          TEXT NOT NULL DEFAULT '보통',
    default_servings     INTEGER NOT NULL DEFAULT 2,
    updated_at           TEXT NOT NULL
);

CREATE TABLE saved_recipes (
    id                INTEGER PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    cuisine           TEXT,
    recipe_json       TEXT NOT NULL,      -- 2단계 레시피 JSON
    source_ingredients TEXT NOT NULL,     -- 추천에 쓴 재료 목록 JSON
    model             TEXT NOT NULL,
    rating            INTEGER CHECK (rating BETWEEN 1 AND 5),
    memo              TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_saved_recipes_user ON saved_recipes(user_id, created_at DESC);
```

- `PRAGMA foreign_keys = ON`을 연결마다 켠다 (탈퇴 시 연쇄 삭제).
- 서버가 처음 시작할 때 테이블이 없으면 만든다.
- `data/` 폴더는 `.gitignore`에 추가한다 (사용자 데이터가 저장소에 올라가지 않게).

## 6. 비기능 요구사항

- **보안:** 모든 SQL은 매개변수 바인딩(`?`)을 쓴다. 상태를 바꾸는 요청(POST/PUT/PATCH/DELETE)은 같은 출처(Origin 헤더)에서 온 것만 받는다. 레시피와 메모를 화면에 넣을 때는 `textContent`를 써서 HTML로 해석되지 않게 한다.
- **비밀 정보:** `FLASK_SECRET_KEY`는 `.env`에 두고 `.env.example`에는 자리표시자만 넣는다. 기존 pre-commit 훅이 `.env`를 막는다.
- **개인정보:** 알레르기와 식습관은 레시피 생성 프롬프트에 들어가 외부 AI 서비스로 전송된다. 프로필 화면에 이 사실을 안내한다. 이름과 아이디는 프롬프트에 넣지 않는다.
- **호환:** 로그인하지 않아도 1, 2단계 기능은 그대로 동작한다.

## 7. 기술 구성

1, 2단계 구조에 다음을 더한다.

- `db.py`: SQLite 연결, 테이블 만들기
- `auth.py`: 가입, 로그인, 비밀번호 해시, 로그인 필요 데코레이터
- `app.py`: 4.4의 API
- `static/`: 로그인, 프로필, 내 레시피 화면

추가 설치는 없다 (Flask와 표준 라이브러리의 `sqlite3`, `hashlib`, `secrets`).

## 8. 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| 비밀번호나 세션 비밀 값이 새어 나간다 | 해시와 salt만 저장하고, 세션 비밀 값은 `.env`에서만 읽는다. |
| 다른 사용자의 레시피에 접근한다 | 모든 조회와 수정 SQL에 `user_id = ?` 조건을 넣고, 접근 테스트를 완료 조건에 둔다. |
| 알레르기 재료가 들어간 레시피를 추천한다 | 2단계의 서버 필터(F2-10)에 프로필 알레르기를 항상 넣고, 저장한 레시피를 볼 때도 경고한다 (F3-16). |
| 무료 모델 사용 한도(하루 50회)를 여러 사용자가 함께 쓴다 | 사용자별 하루 추천 횟수를 표시하고, 로컬 개인 사용을 전제로 한다. 사용자가 늘면 유료 크레딧이나 BYOK를 검토한다. |

## 9. 완료 조건

- [ ] 가입, 로그인, 로그아웃, 탈퇴가 동작하고, 탈퇴하면 그 사용자의 레시피가 DB에서 모두 지워진다.
- [ ] DB 파일 어디에도 비밀번호 원문이 없다.
- [ ] 프로필에 "새우" 알레르기를 넣으면 추천 조건에 자동으로 들어가고, 추천 결과에 새우가 나오지 않는다.
- [ ] 레시피를 저장하고, 서버를 다시 켠 뒤에도 보관함에서 AI 호출 없이 볼 수 있다.
- [ ] 사용자 A로 로그인해서 사용자 B의 레시피 ID로 조회, 수정, 삭제하면 모두 404가 나온다.
- [ ] 메모에 `<script>alert(1)</script>`를 넣어도 스크립트가 실행되지 않고 글자로 보인다.
- [ ] 로그인하지 않은 상태에서도 1, 2단계를 끝까지 쓸 수 있다.
