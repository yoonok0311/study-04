// Created: 2026-09-29 12:57
// 두 페이지(index.html 재료 인식, recipes.html 레시피)가 함께 쓰는 서버 찾기와 진행 상황 읽기

const $ = (id) => document.getElementById(id);

// sessionStorage 키: 1단계 결과(재료 목록), 2단계 상태(조건, 추천 결과)
const STEP1_KEY = "fridge.step1";
const STEP2_KEY = "fridge.step2";

function loadStored(key) {
  try { return JSON.parse(sessionStorage.getItem(key)); } catch (_) { return null; }
}

function saveStored(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); return true; } catch (_) { return false; }
}

// 로컬(파일, 127.0.0.1, localhost)로 열었는지, 배포 주소(Render)로 열었는지
const IS_LOCAL = location.protocol === "file:" || ["127.0.0.1", "localhost"].includes(location.hostname);

const Api = {
  // 서버 주소 후보: 같은 출처(py app.py나 배포 주소로 연 경우) → 기본 로컬 서버.
  // 로컬에서 html을 파일로 열거나 Live Server 등 다른 포트로 열었을 때도 서버를 찾게 함.
  // 배포 주소로 열었을 때는 방문자 컴퓨터의 로컬 서버를 찾지 않음
  candidates: (location.protocol === "file:" ? [] : [""])
    .concat(IS_LOCAL ? ["http://127.0.0.1:5000", "http://localhost:5000"] : []),
  base: null, // 찾은 서버 주소 ("" = 같은 출처), 못 찾으면 null
  // 로컬이면 서버 켜는 법을, 배포 주소면 잠시 뒤 다시 시도하라고 안내.
  // Render 무료 서버는 15분 동안 요청이 없으면 잠들고 깨는 데 30~60초 걸림
  NO_SERVER: IS_LOCAL
    ? "서버에 연결할 수 없습니다. 터미널에서 study-04 폴더로 이동해 "
      + "\"py app.py\"를 실행한 뒤, 브라우저에서 http://127.0.0.1:5000 을 열어 주세요."
    : "서버에 연결할 수 없습니다. 서버가 잠에서 깨는 중일 수 있으니 1분쯤 뒤 다시 시도해 주세요.",

  // AbortSignal.timeout이 없는 브라우저도 있어서 AbortController로 시간 제한
  async probe(base, ms) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    try {
      const response = await fetch(`${base}/api/health`, { cache: "no-store", signal: controller.signal });
      return response.ok && (await response.json()).ok === true;
    } catch (_) {
      return false; // 연결 거부, 시간 초과, 이 서버가 아님(404 HTML 등)
    } finally {
      clearTimeout(timer);
    }
  },

  async find(ms = 3000) {
    for (const base of this.candidates) {
      if (await this.probe(base, ms)) {
        this.base = base;
        return true;
      }
    }
    this.base = null;
    return false;
  },

  // 페이지를 열 때 부름: 서버를 찾을 때까지 조용히 다시 찾음 (서버를 늦게 켜거나 Render가 잠에서 깨는 중일 수 있음).
  // 이미 떠 있는 "서버 없음" 안내는 서버를 찾으면 지움
  watch() {
    const attempt = async () => {
      if (await this.find()) {
        if ($("error").textContent === this.NO_SERVER) hideError();
      } else {
        setTimeout(attempt, 3000);
      }
    };
    attempt();
  },

  // 서버는 진행 상황을 한 줄에 JSON 하나씩(NDJSON) 보냄: retry/status 여러 번 → result 또는 error.
  // result 이벤트를 돌려주고, 진행 문구는 onProgress(text)로 알림. 취소하면 AbortError가 그대로 나감
  async stream(path, init, onProgress) {
    // 사용자가 버튼을 눌렀을 때는 느린 첫 응답(Render 깨우기 등)까지 기다린 뒤에야 안내
    if (this.base === null && !(await this.find(60000))) throw new Error(this.NO_SERVER);
    let response;
    try {
      response = await fetch(`${this.base}${path}`, init);
    } catch (e) {
      if (e.name === "AbortError") throw e;
      this.base = null; // 네트워크 오류: 서버가 꺼짐
      throw new Error(this.NO_SERVER);
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `서버 오류 (${response.status})`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "result") return event;
        if (event.type === "error") throw new Error(event.error);
        if (event.type === "retry") {
          onProgress(`사용자가 많아 다시 시도하는 중 (${event.attempt}/${event.max}) · ${event.wait}초 대기`);
        } else if (event.type === "status") {
          onProgress(event.message);
        }
      }
      if (done) throw new Error("서버 응답이 중간에 끊겼습니다. 다시 시도해 주세요.");
    }
  },
};

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}

function hideError() {
  $("error").hidden = true;
}
