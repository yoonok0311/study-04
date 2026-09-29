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

const Api = {
  // 서버 주소 후보: 같은 출처(py app.py로 연 경우) → 기본 로컬 서버.
  // html을 파일로 열거나 Live Server 등 다른 포트로 열었을 때도 서버를 찾게 함
  candidates: location.protocol === "file:" ? ["http://127.0.0.1:5000"] : ["", "http://127.0.0.1:5000"],
  base: null, // 찾은 서버 주소 ("" = 같은 출처), 못 찾으면 null
  NO_SERVER: "서버에 연결할 수 없습니다. 터미널에서 study-04 폴더로 이동해 "
    + "\"py app.py\"를 실행한 뒤, 브라우저에서 http://127.0.0.1:5000 을 열어 주세요.",

  async find() {
    for (const base of this.candidates) {
      try {
        const response = await fetch(`${base}/api/health`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
        if (response.ok && (await response.json()).ok) {
          this.base = base;
          return true;
        }
      } catch (_) {} // 연결 거부, 시간 초과, 이 서버가 아님(404 HTML 등)
    }
    this.base = null;
    return false;
  },

  // 서버는 진행 상황을 한 줄에 JSON 하나씩(NDJSON) 보냄: retry/status 여러 번 → result 또는 error.
  // result 이벤트를 돌려주고, 진행 문구는 onProgress(text)로 알림. 취소하면 AbortError가 그대로 나감
  async stream(path, init, onProgress) {
    if (this.base === null && !(await this.find())) throw new Error(this.NO_SERVER);
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
