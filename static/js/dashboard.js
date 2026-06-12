/* 엘리스랩 훈련비과정 만족도 대시보드 프론트엔드 */

const PRIMARY = "#5B4EE8";
const PRIMARY_SOFT = "rgba(91, 78, 232, 0.12)";
const charts = {};

/* ---------- 유틸 ---------- */
function $(sel) { return document.querySelector(sel); }

function showOverlay(text) {
  $("#overlay-text").textContent = text || "처리 중...";
  $("#overlay").classList.remove("hidden");
}
function hideOverlay() { $("#overlay").classList.add("hidden"); }

function toast(msg, isError) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function scoreColor(v) {
  if (v >= 4.5) return "#22c55e";
  if (v >= 4.0) return PRIMARY;
  if (v >= 3.0) return "#f59e0b";
  return "#e23b53";
}

// 순위 강조 색상 (금·은·동) — 항목별 평균 / 종합 만족도 순위 상위 3개 구분
const RANK_COLORS = ["#f5a623", "#9aa3b2", "#c77b30"]; // 1위·2위·3위
const RANK_REST = "#b9b2f0"; // 4위 이하 (옅은 퍼플)
const RANK_MEDALS = ["🥇", "🥈", "🥉"];
function rankColor(idx) { return idx < 3 ? RANK_COLORS[idx] : RANK_REST; }

// 리스트의 상위 N개만 노출하고 나머지는 "더보기" 버튼으로 토글한다.
function applyCollapse(listEl, visible) {
  if (!listEl) return;
  const prev = listEl.parentElement.querySelector(".show-more-btn");
  if (prev) prev.remove();

  const rows = Array.from(listEl.children).filter(
    (c) => c.classList.contains("rank-row") || c.classList.contains("item-row")
  );
  if (rows.length <= visible) return;

  const collapse = () => rows.forEach((r, i) => r.classList.toggle("row-hidden", i >= visible));
  collapse();

  const hidden = rows.length - visible;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "show-more-btn";
  btn.textContent = `더보기 (${hidden}개 더) ▾`;
  let expanded = false;
  btn.onclick = () => {
    expanded = !expanded;
    if (expanded) {
      rows.forEach((r) => r.classList.remove("row-hidden"));
      btn.textContent = "접기 ▴";
    } else {
      collapse();
      btn.textContent = `더보기 (${hidden}개 더) ▾`;
    }
  };
  listEl.insertAdjacentElement("afterend", btn);
}

// 글래스모피즘 SVG 아이콘 (그라데이션 url(#glassGrad) 은 HTML defs 에 정의)
const ICONS = {
  category: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><path d="M5 12.5 12.5 5H19a1 1 0 0 1 1 1v6.5L12.5 20a2 2 0 0 1-2.8 0L5 15.3a2 2 0 0 1 0-2.8z" fill="url(#glassGrad)" opacity="0.9"/><circle cx="15.4" cy="8.6" r="1.4" fill="#fff" opacity="0.9"/></svg>`,
  items: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><rect x="4" y="11" width="4.2" height="9" rx="1.6" fill="url(#glassGrad)" opacity="0.5"/><rect x="9.9" y="7" width="4.2" height="13" rx="1.6" fill="url(#glassGrad)" opacity="0.78"/><rect x="15.8" y="4" width="4.2" height="16" rx="1.6" fill="url(#glassGrad)" opacity="1"/></svg>`,
  compare: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="4" fill="url(#glassGrad)" opacity="0.26"/><path d="M6 15l3.6-4 3 2.6L20 7" stroke="url(#glassGrad)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  ranking: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><path d="M7 4h10v4a5 5 0 0 1-10 0z" fill="url(#glassGrad)" opacity="0.92"/><path d="M5 5h2v2.4A2.5 2.5 0 0 1 5 5zM17 5h2a2.5 2.5 0 0 1-2 2.4z" fill="url(#glassGrad)" opacity="0.55"/><rect x="11" y="12" width="2" height="3" fill="url(#glassGrad)" opacity="0.9"/><rect x="9.4" y="15.3" width="5.2" height="2.2" rx="1" fill="url(#glassGrad)" opacity="0.7"/><rect x="7.8" y="17.8" width="8.4" height="2.5" rx="1.2" fill="url(#glassGrad)" opacity="0.95"/></svg>`,
  keywords: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><rect x="11" y="10" width="10" height="8" rx="3.5" fill="url(#glassGrad)" opacity="0.33"/><rect x="3" y="3" width="13" height="10" rx="4" fill="url(#glassGrad)" opacity="0.92"/><path d="M7 12.5v3.2l3.4-3.2z" fill="url(#glassGrad)" opacity="0.92"/><circle cx="7" cy="8" r="1.1" fill="#fff"/><circle cx="9.6" cy="8" r="1.1" fill="#fff"/><circle cx="12.2" cy="8" r="1.1" fill="#fff"/></svg>`,
  extra: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><path d="M6 16v-6a6 6 0 0 1 12 0v6l1.6 2.2a.6.6 0 0 1-.5 1H4.9a.6.6 0 0 1-.5-1z" fill="url(#glassGrad)" opacity="0.9"/><path d="M9.5 19.6a2.5 2.5 0 0 0 5 0z" fill="url(#glassGrad)" opacity="0.95"/><circle cx="18" cy="6" r="2.8" fill="url(#glassGrad)" opacity="0.45"/></svg>`,
  compose: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><rect x="7" y="4" width="13" height="16" rx="3" fill="url(#glassGrad)" opacity="0.33"/><rect x="4" y="6" width="13" height="14" rx="3" fill="url(#glassGrad)" opacity="0.92"/><path d="M7 11h7M7 14.5h7" stroke="#fff" stroke-width="1.4" stroke-linecap="round" opacity="0.85"/></svg>`,
  instructor: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><circle cx="15.5" cy="8.5" r="4" fill="url(#glassGrad)" opacity="0.33"/><circle cx="11.5" cy="8" r="3.7" fill="url(#glassGrad)" opacity="0.95"/><path d="M4.5 20c0-3.9 3.1-6.6 7-6.6s7 2.7 7 6.6z" fill="url(#glassGrad)" opacity="0.9"/></svg>`,
  effect: `<svg class="gicon" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" fill="url(#glassGrad)" opacity="0.26"/><circle cx="12" cy="12" r="5.6" fill="url(#glassGrad)" opacity="0.6"/><circle cx="12" cy="12" r="2.4" fill="url(#glassGrad)" opacity="1"/></svg>`,
};

// 카테고리 아이콘/설명
const CAT_META = {
  "교육 구성": { icon: ICONS.compose, desc: "내용 · 자료 · 환경 · 시간 · 운영" },
  "강사 역량": { icon: ICONS.instructor, desc: "전문성 · 전달력 · 질문응답 · 참여" },
  "교육 효과": { icon: ICONS.effect, desc: "지식습득 · 목표달성 · 실무적용" },
};

// 점수 분포에 맞춰 차트 축 최소값을 자동 계산(미세한 차이를 강조)
function axisMin(values) {
  const valid = values.filter((v) => v > 0);
  if (!valid.length) return 0;
  const lo = Math.min(...valid);
  return Math.max(0, Math.floor((lo - 0.2) * 2) / 2);
}

// 강좌별 비교 차트용 팔레트
const COMPARE_COLORS = [
  "#5B4EE8", "#FF6B6B", "#22C55E", "#F59E0B",
  "#06B6D4", "#EC4899", "#8B5CF6", "#10B981",
  "#F43F5E", "#3B82F6",
];

/* ---------- 업로드 ---------- */
async function uploadFile(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  showOverlay("데이터를 분석하는 중...");
  try {
    const res = await fetch("/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "업로드 실패");
    toast(`'${data.filename}' 업로드 완료 (${data.rows}건)`);
    populateCourses(data.courses, "전체");
    $("#side-filename").textContent = data.filename;
    $("#subtitle").textContent = `${data.filename} · 응답 ${data.rows}건`;
    await loadDashboard("전체");
  } catch (e) {
    toast(e.message, true);
  } finally {
    hideOverlay();
  }
}

let currentCourse = "전체";
let lastVersion = -1;          // 서버 데이터 버전(자동 새로고침 변경 감지용)
const REFRESH_MS = 20000;      // 20초마다 새 응답 여부 확인

function populateCourses(courses, selected) {
  currentCourse = selected || "전체";
  const sel = $("#course-filter");
  sel.innerHTML = "";
  ["전체", ...(courses || [])].forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    sel.appendChild(opt);
  });
  sel.value = currentCourse;
  sel.onchange = (e) => {
    currentCourse = e.target.value;
    loadDashboard(currentCourse);
  };
}

/* ---------- 대시보드 로드 ---------- */
// silent=true 이면 오버레이 없이 조용히 갱신한다(자동 새로고침용).
async function loadDashboard(course, silent) {
  if (!silent) showOverlay("대시보드를 갱신하는 중...");
  try {
    const res = await fetch(`/api/dashboard?course=${encodeURIComponent(course)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "데이터 로드 실패");
    if (typeof data.version === "number") lastVersion = data.version;
    $("#empty-state").classList.add("hidden");
    $("#dashboard").classList.remove("hidden");
    render(data);
  } catch (e) {
    if (!silent) toast(e.message, true);
  } finally {
    if (!silent) hideOverlay();
  }
}

/* ---------- 렌더링 ---------- */
function render(d) {
  renderKpi(d.kpi);
  renderCategories(d.categories);
  renderItems(d.items, d.categories);
  renderCompare(d.item_order, d.course_scores, d.selected_course);
  renderRanking(d.course_ranking, d.selected_course);
  renderKeywords(d.keywords, d.ai_analysis);
  renderNewsletter(d.newsletter);
  renderWished(d.wished_courses);
  renderWishedOther(d.wished_other);
}

function renderKpi(k) {
  $("#kpi-overall").textContent = (k.overall || 0).toFixed(2);
  $("#kpi-instructor").textContent = (k.instructor || 0).toFixed(2);
  $("#kpi-effect").textContent = (k.effect || 0).toFixed(2);
  $("#kpi-respondents").textContent = k.respondents;
  $("#kpi-courses-sub").textContent = `${k.course_count}개 강좌`;
}

function renderCategories(cats) {
  const grid = $("#category-grid");
  grid.innerHTML = "";
  cats.forEach((c) => {
    const pct = Math.max(0, Math.min(100, (c.score / 5) * 100));
    const m = CAT_META[c.name] || { icon: ICONS.category, desc: "" };
    const el = document.createElement("div");
    el.className = "cat-card";
    el.innerHTML = `
      <div class="cat-icon">${m.icon}</div>
      <div class="cat-name">${c.name}</div>
      <div class="cat-score">${c.score.toFixed(2)}<small> /5</small></div>
      <div class="cat-desc">${m.desc}</div>
      <div class="progress"><span style="width:${pct}%"></span></div>`;
    grid.appendChild(el);
  });
}

function renderItems(items, categories) {
  // 점수순 정렬(내림차순)
  const sorted = [...items].sort((a, b) => b.score - a.score);
  const labels = sorted.map((i) => i.name);
  const scores = sorted.map((i) => i.score);
  const lo = axisMin(scores);

  // 막대 차트 (가로) — 상위 3개 금·은·동, 나머지 옅은 퍼플
  drawChart("bar-chart", {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "평균 점수",
        data: scores,
        backgroundColor: scores.map((_, idx) => rankColor(idx)),
        borderRadius: 6,
        maxBarThickness: 26,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: (t) => sorted[t[0].dataIndex].name } },
      },
      scales: {
        x: { min: lo, max: 5, ticks: { stepSize: 0.5 }, grid: { color: "#f3f4f6" } },
        y: { ticks: { font: { size: 12 } }, grid: { display: false } },
      },
    },
  });

  // 레이더 — 전체 항목(12개)을 축으로
  const radarItems = [...items]; // 원래 항목 순서 유지(축 안정)
  const radarLabels = radarItems.map((i) => i.name);
  const radarScores = radarItems.map((i) => i.score);
  const rValid = radarScores.filter((v) => v > 0);
  const rLo = rValid.length ? Math.max(0, Math.floor((Math.min(...rValid) - 0.1) * 4) / 4) : 0;
  drawChart("radar-chart", {
    type: "radar",
    data: {
      labels: radarLabels,
      datasets: [{
        label: "항목별 평균",
        data: radarScores,
        backgroundColor: "rgba(91, 78, 232, 0.15)",
        borderColor: PRIMARY,
        borderWidth: 2,
        pointBackgroundColor: PRIMARY,
        pointRadius: 4,
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.parsed.r.toFixed(2)}` } },
      },
      scales: {
        r: {
          min: rLo, max: 5,
          ticks: { stepSize: 0.25, font: { size: 10 }, backdropColor: "transparent" },
          pointLabels: {
            font: { size: 10, weight: "600" },
            callback: (label) => (label.length > 11 ? label.slice(0, 10) + "…" : label),
          },
        },
      },
    },
  });

  // 최고 / 최저 항목 하이라이트
  const hi = sorted[0], low = sorted[sorted.length - 1];
  $("#highlight-row").innerHTML = `
    <div class="highlight best">
      <span class="h-badge">🏆</span>
      <div><div class="h-label">가장 높은 항목</div><div class="h-name">${hi.name}</div></div>
      <span class="h-score">${hi.score.toFixed(2)}</span>
    </div>
    <div class="highlight worst">
      <span class="h-badge">📌</span>
      <div><div class="h-label">개선이 필요한 항목</div><div class="h-name">${low.name}</div></div>
      <span class="h-score">${low.score.toFixed(2)}</span>
    </div>`;

  // 상세 리스트 (점수순) — 상위 3개 메달 강조
  const list = $("#item-list");
  list.innerHTML = "";
  sorted.forEach((i, idx) => {
    const pct = Math.max(2, Math.min(100, (i.score / 5) * 100));
    const catTag = i.category ? i.category.split(" ").pop() : "";
    const isTop = idx < 3;
    const medal = isTop ? RANK_MEDALS[idx] + " " : "";
    const barColor = isTop ? RANK_COLORS[idx] : RANK_REST;
    const scoreCol = isTop ? RANK_COLORS[idx] : "var(--text)";
    const row = document.createElement("div");
    row.className = "item-row" + (isTop ? ` top${idx + 1}` : "");
    row.innerHTML = `
      <div class="item-code">${catTag}</div>
      <div>
        <div class="item-label">${medal}${i.name}</div>
        <div class="item-cat">${i.category || ""}</div>
      </div>
      <div class="item-bar"><span style="width:${pct}%;background:${barColor}"></span></div>
      <div class="item-score" style="color:${scoreCol}">${i.score.toFixed(2)}</div>`;
    list.appendChild(row);
  });

  applyCollapse(list, 3); // 상위 3개만 노출, 나머지는 더보기
}

function renderCompare(itemOrder, courseScores, selected) {
  if (!itemOrder || !courseScores) return;
  const courses = Object.keys(courseScores);
  const datasets = courses.map((c, idx) => {
    const color = COMPARE_COLORS[idx % COMPARE_COLORS.length];
    const isSel = selected && selected !== "전체" && c === selected;
    return {
      label: c.length > 22 ? c.slice(0, 21) + "…" : c,
      data: itemOrder.map((n) => courseScores[c][n] ?? null),
      borderColor: color,
      backgroundColor: color,
      borderWidth: isSel ? 4 : 2,
      pointRadius: isSel ? 4 : 2,
      tension: 0.3,
    };
  });
  const allVals = courses.flatMap((c) => Object.values(courseScores[c]));
  drawChart("compare-chart", {
    type: "line",
    data: { labels: itemOrder, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
      },
      scales: {
        y: { min: axisMin(allVals), max: 5, ticks: { stepSize: 0.5 }, grid: { color: "#f3f4f6" } },
        x: { ticks: { font: { size: 11 }, maxRotation: 40 }, grid: { display: false } },
      },
    },
  });
}

function renderRanking(rows, selected) {
  const list = $("#ranking-list");
  list.innerHTML = "";
  if (!rows.length) { list.innerHTML = '<p class="card-hint">데이터가 없습니다.</p>'; return; }
  rows.forEach((r, idx) => {
    const pct = Math.max(0, Math.min(100, (r.score / 5) * 100));
    const row = document.createElement("div");
    row.className = "rank-row" + (idx < 3 ? ` top${idx + 1}` : "");
    if (r.course === selected) row.style.background = "var(--primary-soft)";
    row.innerHTML = `
      <div class="rank-num">${idx + 1}</div>
      <div>
        <div class="rank-name">${r.course}</div>
        <div class="rank-meta">응답 ${r.count}명</div>
      </div>
      <div class="rank-bar"><span style="width:${pct}%"></span></div>
      <div class="rank-score">${r.score.toFixed(2)}</div>`;
    list.appendChild(row);
  });

  applyCollapse(list, 3); // 상위 3개만 노출, 나머지는 더보기
}

const POS_PALETTE = ["#5B4EE8", "#7d70ff", "#4a3fd0", "#9b8fff", "#6f63f0", "#b3a9ff"];
const NEG_PALETTE = ["#ea580c", "#f59e0b", "#fb923c", "#d97706", "#fdba74", "#f97316"];

// 키워드 데이터를 {word, count} 형태로 정규화 (AI는 keyword, 규칙기반은 word)
function normKw(items) {
  return (items || []).map((x) => ({
    word: x.word || x.keyword || "",
    count: x.count || 1,
  })).filter((x) => x.word);
}

function renderKeywords(keywords, ai) {
  const tag = $("#kw-engine");
  const summary = $("#ai-summary");
  const aiValid = ai && !ai.error &&
    ((ai.positive && ai.positive.length) || (ai.negative && ai.negative.length));

  let pos, neg, summaryText;
  if (aiValid) {
    pos = normKw(ai.positive); neg = normKw(ai.negative);
    summaryText = ai.summary || "";
    tag.textContent = "Claude AI 분석";
  } else {
    pos = normKw(keywords && keywords.positive); neg = normKw(keywords && keywords.negative);
    summaryText = "";
    tag.textContent = "규칙 기반 분석";
  }

  if (summaryText) {
    summary.style.display = "flex";
    summary.innerHTML = `<span class="ai-summary-icon">📝</span><p>${summaryText}</p>`;
  } else {
    summary.style.display = "none";
  }

  renderTagcloud($("#kw-positive"), pos, "pos");
  renderTagcloud($("#kw-negative"), neg, "neg");
}

function renderTagcloud(el, items, kind) {
  el.innerHTML = "";
  if (!items || !items.length) {
    el.innerHTML = '<p class="card-hint">추출된 키워드가 없습니다.</p>';
    return;
  }
  const counts = items.map((i) => i.count || 1);
  const max = Math.max(...counts), min = Math.min(...counts);
  const palette = kind === "pos" ? POS_PALETTE : NEG_PALETTE;
  items.forEach((it, i) => {
    const ratio = max === min ? 0.6 : (it.count - min) / (max - min);
    const size = 15 + ratio * 25; // 15 ~ 40px (빈도 비례)
    const span = document.createElement("span");
    span.className = "tag";
    span.textContent = it.word;
    span.style.fontSize = size.toFixed(0) + "px";
    span.style.color = palette[i % palette.length];
    span.style.opacity = (0.6 + ratio * 0.4).toFixed(2);
    span.title = `${it.word} · ${it.count}회`;
    el.appendChild(span);
  });
}

function renderNewsletter(n) {
  const yes = n["네"] || 0;
  const no = n["아니오"] || 0;
  const total = yes + no;
  const pctYes = total ? ((yes / total) * 100).toFixed(1) : "0.0";
  const pctNo = total ? ((no / total) * 100).toFixed(1) : "0.0";

  $("#news-stats").innerHTML = `
    <div class="news-stat agree">
      <div class="ns-label">수신 동의</div>
      <div class="ns-value">${yes}명</div>
      <div class="ns-sub">${pctYes}%</div>
    </div>
    <div class="news-stat disagree">
      <div class="ns-label">수신 거부</div>
      <div class="ns-value">${no}명</div>
      <div class="ns-sub">${pctNo}%</div>
    </div>
    <div class="news-stat total">
      <div class="ns-label">전체 응답</div>
      <div class="ns-value">${total}명</div>
      <div class="ns-sub">동의율 ${pctYes}%</div>
    </div>`;

  drawChart("news-chart", {
    type: "doughnut",
    data: {
      labels: ["수신 동의", "수신 거부"],
      datasets: [{
        data: [yes, no],
        backgroundColor: [PRIMARY, "#e3e1f5"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: "65%",
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const t = yes + no || 1;
              const pct = ((ctx.parsed / t) * 100).toFixed(1);
              return ` ${ctx.label}: ${ctx.parsed}명 (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

function renderWished(rows) {
  const list = $("#wished-list");
  list.innerHTML = "";
  if (!rows.length) { list.innerHTML = '<p class="card-hint">응답이 없습니다.</p>'; return; }
  const max = Math.max(...rows.map((r) => r.count));
  rows.forEach((r, idx) => {
    const pct = Math.max(6, (r.count / max) * 100);
    const row = document.createElement("div");
    row.className = "rank-row" + (idx < 3 ? ` top${idx + 1}` : "");
    row.innerHTML = `
      <div class="rank-num">${idx + 1}</div>
      <div><div class="rank-name">${r.course}</div></div>
      <div class="rank-bar"><span style="width:${pct}%"></span></div>
      <div class="rank-score">${r.count}</div>`;
    list.appendChild(row);
  });

  applyCollapse(list, 3);
}

// 희망 과정 자유입력(기타) 의견 목록 — 자유 텍스트라 textContent 로 안전하게 렌더
function renderWishedOther(rows) {
  const box = $("#wished-other-list");
  if (!box) return;
  box.innerHTML = "";
  if (!rows || !rows.length) {
    box.innerHTML = '<p class="card-hint">직접입력 의견이 없습니다.</p>';
    return;
  }
  rows.forEach((r) => {
    const item = document.createElement("div");
    item.className = "other-item";
    const txt = document.createElement("span");
    txt.className = "other-text";
    txt.textContent = r.text;
    item.appendChild(txt);
    if (r.count > 1) {
      const cnt = document.createElement("span");
      cnt.className = "other-count";
      cnt.textContent = "×" + r.count;
      item.appendChild(cnt);
    }
    box.appendChild(item);
  });
}

function drawChart(id, config) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, config);
}

/* ---------- 이벤트 ---------- */
function init() {
  // 섹션 제목에 글래스모피즘 아이콘 주입
  document.querySelectorAll(".section-title[data-icon]").forEach((h) => {
    const name = h.getAttribute("data-icon");
    if (ICONS[name]) h.insertAdjacentHTML("afterbegin", ICONS[name]);
  });

  // 업로드 UI 제거(자동 모드). 파일 입력이 있으면만 바인딩(하위호환).
  const fi = $("#file-input");
  if (fi) fi.addEventListener("change", (e) => uploadFile(e.target.files[0]));
  const fi2 = $("#file-input-2");
  if (fi2) fi2.addEventListener("change", (e) => uploadFile(e.target.files[0]));

  // 사이드바 활성 표시
  document.querySelectorAll(".nav-item").forEach((a) => {
    a.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((x) => x.classList.remove("active"));
      a.classList.add("active");
    });
  });

  // 이미 수집된 데이터가 있으면 바로 로드
  fetch("/api/status")
    .then((r) => r.json())
    .then((s) => {
      if (s.has_data) {
        applyStatus(s);
        loadDashboard(currentCourse);
      }
    })
    .catch(() => {});

  // 자동 새로고침: 주기적으로 status 를 확인해 version 이 바뀌면 조용히 다시 로드
  setInterval(checkForUpdates, REFRESH_MS);
}

// status 응답으로 강좌 목록/부제목을 갱신한다.
function applyStatus(s) {
  const prev = currentCourse;
  populateCourses(s.courses, s.courses.includes(prev) ? prev : "전체");
  $("#side-filename").textContent = s.filename;
  $("#subtitle").textContent = `${s.filename} · 응답 ${s.rows}건`;
}

// 새 응답 감지 시 화면을 조용히(오버레이 없이) 갱신한다.
async function checkForUpdates() {
  try {
    const s = await (await fetch("/api/status")).json();
    if (!s.has_data) return;
    if (s.version === lastVersion) return;   // 변경 없음
    applyStatus(s);
    await loadDashboard(currentCourse, true); // silent
    toast(`새 응답 반영됨 (총 ${s.rows}건)`);
  } catch (e) {
    /* 네트워크 일시 오류는 무시 */
  }
}

document.addEventListener("DOMContentLoaded", init);
