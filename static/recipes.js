// Created: 2026-09-29 12:57
// 1단계 재료 목록 + 조건 → 서버(/api/recipes)로 레시피 추천 → 목록과 상세 (PRD_step2.md)

const OPTION_IDS = ["servings", "max_time", "difficulty", "cuisine", "avoid", "basic_seasonings", "only_owned"];

// 화면 상태 (STEP2_KEY에 저장). sourceSig: 1단계 재료 목록이 바뀌었는지 알아보는 값
// removed: 이번 추천에서 뺀 재료 이름, recipes: 서버가 준 레시피 (재료마다 have 표시),
// selected: 상세로 보고 있는 레시피 번호, done: 레시피 제목 → 완료한 단계 번호들
let state = { sourceSig: "", removed: [], options: null, recipes: null, meta: null, selected: null, done: {} };
let step1Ingredients = [];
let controller = null;

// ---------- 저장과 복원 ----------

function save() {
  saveStored(STEP2_KEY, state);
}

function restore() {
  const step1 = loadStored(STEP1_KEY);
  step1Ingredients = (step1 && step1.ingredients) || [];
  const sig = JSON.stringify(step1Ingredients.map((i) => i.name));
  const saved = loadStored(STEP2_KEY);
  if (saved) state = { ...state, ...saved };
  // 1단계에서 재료를 다시 인식하거나 고쳤으면 뺀 재료와 이전 추천은 버림 (조건은 유지)
  if (state.sourceSig !== sig) {
    state = { ...state, sourceSig: sig, removed: [], recipes: null, meta: null, selected: null, done: {} };
    save();
  }
}

function currentIngredients() {
  return step1Ingredients
    .filter((i) => !state.removed.includes(i.name))
    .map(({ name, name_en, quantity }) => ({ name, name_en: name_en || "", quantity: quantity || "" }));
}

// ---------- 조건 입력 ----------

function readOptions() {
  const options = {};
  for (const key of OPTION_IDS) {
    const el = $(`opt-${key}`);
    options[key] = el.type === "checkbox" ? el.checked : el.value;
  }
  options.servings = Number(options.servings);
  options.avoid = options.avoid.split(",").map((s) => s.trim()).filter(Boolean);
  return options;
}

function writeOptions(options) {
  for (const key of OPTION_IDS) {
    if (!(key in options)) continue;
    const el = $(`opt-${key}`);
    if (el.type === "checkbox") el.checked = !!options[key];
    else el.value = key === "avoid" ? options.avoid.join(", ") : String(options[key]);
  }
}

// ---------- 서버 요청 ----------

async function requestRecipes(count, excludeTitles) {
  hideError();
  controller = new AbortController();
  setBusy(true, count === 1 ? "다른 레시피를 만드는 중…" : "레시피를 만드는 중… (보통 20초 안팎)");
  const body = { ingredients: currentIngredients(), options: state.options, count, exclude_titles: excludeTitles };
  try {
    return await Api.stream("/api/recipes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    }, (text) => setBusy(true, text));
  } catch (e) {
    showError(e.name === "AbortError" ? "추천을 취소했습니다." : e.message);
    return null;
  } finally {
    controller = null;
    setBusy(false);
  }
}

async function recommend() {
  state.options = readOptions();
  save();
  const result = await requestRecipes(3, []);
  if (!result) return;
  state.recipes = result.recipes;
  state.meta = { model: result.model, elapsed: result.elapsed_sec, note: result.note, cached: !!result.cached };
  state.selected = null;
  state.done = {};
  save();
  render();
  $("results-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

// 한 레시피만 새로 받기: 지금 보이는 레시피 이름을 모두 빼 달라고 보냄 (F2-11)
async function replaceRecipe(index) {
  const result = await requestRecipes(1, state.recipes.map((r) => r.title));
  if (!result || !result.recipes.length) return;
  delete state.done[state.recipes[index].title];
  state.recipes[index] = result.recipes[0];
  save();
  render();
}

// ---------- 화면 그리기 ----------

function setBusy(busy, text) {
  $("progress").hidden = !busy;
  if (text) $("progress-text").textContent = text;
  $("recommend-button").disabled = busy;
  document.querySelectorAll(".replace-button, .chip button").forEach((b) => { b.disabled = busy; });
}

function tagList(recipe) {
  const tags = [];
  if (recipe.time_minutes) tags.push(`⏱ ${recipe.time_minutes}분`);
  tags.push(recipe.difficulty);
  if (recipe.cuisine) tags.push(recipe.cuisine);
  if (recipe.servings) tags.push(`${recipe.servings}인분`);
  return tags;
}

function renderTags(container, recipe) {
  container.replaceChildren(...tagList(recipe).map((text) => {
    const span = document.createElement("span");
    span.className = "tag";
    span.textContent = text;
    return span;
  }));
}

function render() {
  // 재료 칩
  const ingredients = currentIngredients();
  $("ingredient-count").textContent = `${ingredients.length}개`;
  $("chips").replaceChildren(...step1Ingredients.map((item) => {
    const li = document.createElement("li");
    const removed = state.removed.includes(item.name);
    li.className = "chip" + (removed ? " removed" : "");
    const label = document.createElement("span");
    label.textContent = item.name;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = removed ? "+" : "×";
    button.setAttribute("aria-label", removed ? `${item.name} 다시 넣기` : `${item.name} 빼기`);
    button.addEventListener("click", () => {
      state.removed = removed ? state.removed.filter((n) => n !== item.name) : [...state.removed, item.name];
      save();
      render();
    });
    li.append(label, button);
    return li;
  }));
  $("recommend-button").disabled = ingredients.length === 0;

  // 추천 목록
  const recipes = state.recipes;
  $("results-section").hidden = !recipes || state.selected !== null;
  $("detail-section").hidden = !recipes || state.selected === null;
  if (!recipes) return;

  const meta = [];
  if (state.meta.elapsed != null) meta.push(`${state.meta.elapsed}초`);
  if (state.meta.cached) meta.push("이전 결과 재사용");
  if (state.meta.model) meta.push(state.meta.model);
  $("results-meta").textContent = meta.join(" · ");
  $("results-note").hidden = !state.meta.note;
  $("results-note").textContent = state.meta.note || "";

  $("recipe-list").replaceChildren(...recipes.map((recipe, index) => {
    const card = $("recipe-card-template").content.firstElementChild.cloneNode(true);
    card.querySelector(".recipe-title").textContent = recipe.title;
    card.querySelector(".recipe-summary").textContent = recipe.summary;
    renderTags(card.querySelector(".tags"), recipe);
    const ratio = recipe.total_count ? recipe.have_count / recipe.total_count : 0;
    card.querySelector(".have-bar span").style.width = `${Math.round(ratio * 100)}%`;
    const missing = recipe.total_count - recipe.have_count;
    card.querySelector(".have-text").textContent =
      `재료 ${recipe.have_count}/${recipe.total_count}` + (missing ? ` · ${missing}개 구매 필요` : " · 모두 있음");
    card.querySelector(".open-button").addEventListener("click", () => openDetail(index));
    card.querySelector(".replace-button").addEventListener("click", () => replaceRecipe(index));
    return card;
  }));

  if (state.selected !== null) renderDetail(recipes[state.selected]);
}

function renderDetail(recipe) {
  $("detail-title").textContent = recipe.title;
  $("detail-summary").textContent = recipe.summary;
  renderTags($("detail-tags"), recipe);
  $("detail-have").textContent = `(가진 재료 ${recipe.have_count}/${recipe.total_count})`;

  $("detail-ingredients").replaceChildren(...recipe.ingredients.map((item) => {
    const li = document.createElement("li");
    li.className = item.have ? "have-item" : "need-item";
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = item.have ? "✓" : "구매 필요";
    const name = document.createElement("span");
    name.className = "item-name";
    name.textContent = item.name;
    const amount = document.createElement("span");
    amount.className = "item-amount";
    amount.textContent = item.amount;
    li.append(mark, name, amount);
    return li;
  }));

  const done = state.done[recipe.title] || [];
  $("detail-steps").replaceChildren(...recipe.steps.map((step, index) => {
    const li = document.createElement("li");
    li.textContent = step;
    li.tabIndex = 0;
    li.classList.toggle("done", done.includes(index));
    const toggle = () => {
      const list = state.done[recipe.title] || [];
      state.done[recipe.title] = list.includes(index) ? list.filter((i) => i !== index) : [...list, index];
      li.classList.toggle("done");
      save();
    };
    li.addEventListener("click", toggle);
    li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    return li;
  }));

  $("detail-tips").hidden = !recipe.tips;
  $("detail-tips").textContent = recipe.tips ? `💡 ${recipe.tips}` : "";
}

function openDetail(index) {
  state.selected = index;
  save();
  render();
  $("detail-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- 이벤트 연결 ----------

function init() {
  restore();
  // 1단계 재료가 없으면 1단계로 돌려보냄 (F2-1)
  if (!step1Ingredients.length) {
    location.replace("index.html");
    return;
  }
  if (state.options) writeOptions(state.options);

  $("options-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (!controller) recommend();
  });
  $("cancel-button").addEventListener("click", () => controller && controller.abort());
  $("back-button").addEventListener("click", () => {
    state.selected = null;
    save();
    render();
    $("results-section").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  render();
  Api.find().then((found) => { if (!found) showError(Api.NO_SERVER); });
}

init();
