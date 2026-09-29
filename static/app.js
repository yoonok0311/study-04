// Created: 2026-09-29 11:59
// 냉장고 사진 업로드 → 서버(/api/ingredients)로 재료 인식 → 결과 편집 (PRD_step1.md)

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_SIDE = 1280;       // 보내기 전에 긴 변을 이 크기 이하로 줄임
const JPEG_QUALITY = 0.85;
const THUMB_SIDE = 480;      // 새로 고침 뒤 미리보기 복원용 (sessionStorage 용량 절약)
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const CATEGORIES = ["채소", "과일", "육류", "해산물", "유제품/달걀", "가공식품", "양념/소스", "음료", "기타"];
const BADGES = { low: "확인 필요", user: "직접 추가" };

// 화면 상태. ingredients 항목: { name, name_en, name_suspect, quantity, category, confidence }
// name_suspect: 서버가 한글 이름이 깨졌다고 본 재료 (예: "달/year"). 사용자가 이름을 고치면 false
let state = { thumb: null, ingredients: null, notes: "", model: "", elapsed: null, cached: false };
let uploadBlob = null;       // 줄인 이미지 (메모리에만 둠)
let previewUrl = null;       // uploadBlob의 object URL
let controller = null;       // 진행 중인 요청 취소용

// ---------- 저장과 복원 ----------

function save() {
  // 용량 초과 등으로 실패하면 미리보기 없이라도 목록은 남김
  if (!saveStored(STEP1_KEY, state)) saveStored(STEP1_KEY, { ...state, thumb: null });
}

function restore() {
  const saved = loadStored(STEP1_KEY);
  if (saved) state = { ...state, ...saved };
}

// ---------- 이미지 처리 ----------

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("이미지를 읽을 수 없습니다.")); };
    img.src = url;
  });
}

function drawScaled(img, maxSide) {
  const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.naturalWidth * scale);
  canvas.height = Math.round(img.naturalHeight * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; // 투명 PNG를 JPEG로 바꿀 때 검게 되지 않게
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas;
}

async function handleFile(file) {
  if (!file) return;
  hideError();
  if (!ACCEPTED_TYPES.includes(file.type)) {
    showError("JPG/PNG/WEBP로 올려 주세요.");
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    showError("사진이 너무 큽니다 (최대 20MB).");
    return;
  }
  let img;
  try {
    img = await loadImage(file);
  } catch (e) {
    showError(e.message);
    return;
  }
  uploadBlob = await new Promise((resolve) =>
    drawScaled(img, MAX_SIDE).toBlob(resolve, "image/jpeg", JPEG_QUALITY));
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(uploadBlob);
  // 사진을 바꾸면 이전 인식 결과를 지움 (F1-5)
  state = { thumb: drawScaled(img, THUMB_SIDE).toDataURL("image/jpeg", 0.7),
            ingredients: null, notes: "", model: "", elapsed: null, cached: false };
  save();
  render();
}

// ---------- 서버 요청 ----------

async function recognize() {
  if (!uploadBlob) return;
  hideError();
  controller = new AbortController();
  setBusy(true, "재료를 인식하는 중…");

  const form = new FormData();
  form.append("image", uploadBlob, "fridge.jpg");
  try {
    const result = await Api.stream("/api/ingredients", { method: "POST", body: form, signal: controller.signal },
                                    (text) => setBusy(true, text));
    state = { ...state, ingredients: result.ingredients, notes: result.notes,
              model: result.model, elapsed: result.elapsed_sec, cached: !!result.cached };
    save();
  } catch (e) {
    showError(e.name === "AbortError" ? "인식을 취소했습니다." : e.message);
  } finally {
    controller = null;
    setBusy(false);
    render();
  }
}

// ---------- 화면 그리기 ----------

function setBusy(busy, text) {
  $("progress").hidden = !busy;
  if (text) $("progress-text").textContent = text;
  for (const id of ["recognize-button", "change-button", "pick-button", "camera-button"]) {
    $(id).disabled = busy;
  }
}

function render() {
  // 사진 영역
  const hasPhoto = !!state.thumb;
  $("preview").hidden = !hasPhoto;
  if (hasPhoto) $("preview").src = previewUrl || state.thumb;
  $("dropzone-empty").hidden = hasPhoto;
  $("photo-actions").hidden = !hasPhoto;
  // 새로 고침 뒤에는 원본이 없어서 다시 인식할 수 없음 → 다른 사진만 고를 수 있게
  $("recognize-button").hidden = !uploadBlob;
  $("recognize-button").textContent = state.ingredients ? "다시 인식하기" : "재료 인식하기";

  // 결과 영역
  const list = state.ingredients;
  $("result-section").hidden = !list;
  if (!list) return;

  $("ingredient-count").textContent = `${list.length}개`;
  const meta = [];
  if (state.elapsed != null) meta.push(`${state.elapsed}초`);
  if (state.cached) meta.push("이전 결과 재사용");
  if (state.model) meta.push(state.model);
  $("result-meta").textContent = meta.join(" · ");
  $("notes").hidden = !state.notes;
  $("notes").textContent = state.notes;
  $("empty-message").hidden = list.length > 0;
  $("next-button").disabled = list.length === 0;

  const groups = $("groups");
  groups.replaceChildren();
  for (const category of CATEGORIES) {
    const items = list.map((item, index) => ({ item, index })).filter(({ item }) => item.category === category);
    if (!items.length) continue;
    const section = document.createElement("div");
    section.className = "group";
    const title = document.createElement("h3");
    title.textContent = `${category} (${items.length})`;
    const ul = document.createElement("ul");
    for (const { item, index } of items) ul.appendChild(renderIngredient(item, index));
    section.append(title, ul);
    groups.appendChild(section);
  }
}

function renderIngredient(item, index) {
  const li = $("ingredient-template").content.firstElementChild.cloneNode(true);
  const name = li.querySelector(".name");
  const quantity = li.querySelector(".quantity");
  const badge = li.querySelector(".badge");
  const nameEn = li.querySelector(".name-en");
  name.value = item.name;
  quantity.value = item.quantity;
  if (item.name_en) name.title = `영어 이름: ${item.name_en}`;
  // 이름이 깨졌으면 확신도와 상관없이 "확인 필요" + 영어 이름을 힌트로 보여 줌
  const level = item.name_suspect ? "low" : item.confidence;
  badge.textContent = BADGES[level] || "";
  badge.className = `badge ${level}`;
  badge.hidden = !BADGES[level];
  if (item.name_suspect) badge.title = "AI가 쓴 이름이 깨졌을 수 있습니다. 이름을 확인해 주세요.";
  nameEn.hidden = !(item.name_suspect && item.name_en);
  nameEn.textContent = item.name_en ? `영어 이름: ${item.name_en}` : "";

  // 목록을 다시 그리지 않고 값만 바꿔 저장 (입력 중 포커스 유지)
  name.addEventListener("change", () => {
    const value = name.value.trim();
    if (!value) { name.value = item.name; return; }
    if (value === item.name) return;
    item.name = value;
    if (item.name_suspect) {
      item.name_suspect = false; // 사용자가 고쳤으므로 표시를 없앰
      save();
      render();
      return;
    }
    save();
  });
  quantity.addEventListener("change", () => {
    item.quantity = quantity.value.trim();
    save();
  });
  li.querySelector(".delete").addEventListener("click", () => {
    state.ingredients.splice(index, 1);
    save();
    render();
  });
  return li;
}

// ---------- 이벤트 연결 ----------

function init() {
  for (const category of CATEGORIES) {
    const option = document.createElement("option");
    option.value = option.textContent = category;
    $("add-category").appendChild(option);
  }
  $("add-category").value = "기타";

  $("pick-button").addEventListener("click", () => $("file-input").click());
  $("camera-button").addEventListener("click", () => $("camera-input").click());
  $("change-button").addEventListener("click", () => $("file-input").click());
  for (const id of ["file-input", "camera-input"]) {
    $(id).addEventListener("change", (e) => {
      handleFile(e.target.files[0]);
      e.target.value = ""; // 같은 파일을 다시 골라도 change가 나게
    });
  }

  const dropzone = $("dropzone");
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (!controller) handleFile(e.dataTransfer.files[0]);
  });

  $("recognize-button").addEventListener("click", recognize);
  $("cancel-button").addEventListener("click", () => controller && controller.abort());

  $("add-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("add-name").value.trim();
    if (!name) return;
    state.ingredients.push({ name, quantity: $("add-quantity").value.trim(),
                             category: $("add-category").value, confidence: "user" });
    $("add-name").value = "";
    $("add-quantity").value = "";
    save();
    render();
    $("add-name").focus();
  });

  // 편집한 재료 목록은 이미 sessionStorage(STEP1_KEY)에 있으므로 2단계 페이지로 넘어가기만 함 (F1-17)
  $("next-button").addEventListener("click", () => { location.href = "recipes.html"; });

  restore();
  render();
  Api.watch(); // 서버를 찾을 때까지 조용히 다시 찾음
}

init();
