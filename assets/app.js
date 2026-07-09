"use strict";

const KST_DATE = { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" };
const KST_FULL = { ...KST_DATE, hour: "2-digit", minute: "2-digit" };

async function loadJSON(path) {
  try {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("load failed:", path, err);
    return null;
  }
}

function fmtDate(iso, opts = KST_DATE) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : new Intl.DateTimeFormat("ko-KR", opts).format(d);
}

function escapeHTML(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function el(tag, cls, html) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html != null) node.innerHTML = html;
  return node;
}

// --- search -----------------------------------------------------------------
// No backend/embeddings on a static site, so "의미 검색" is approximated with
// bilingual synonym expansion + relevance ranking: a Korean query still matches
// English article text (예측 -> prediction/forecast), and related terms co-match.
const SYNONYMS = [
  ["예측", "예보", "prediction", "predict", "predictive", "forecast", "forecasting"],
  ["모델", "모델링", "model", "modeling", "models"],
  ["학습", "훈련", "training", "train", "파인튜닝", "finetuning", "fine-tuning"],
  ["에이전트", "agent", "agents", "agentic"],
  ["데이터", "데이터셋", "data", "dataset", "datasets"],
  ["통계", "통계학", "statistics", "stats", "statistical"],
  ["라이브러리", "패키지", "library", "libraries", "package", "packages"],
  ["프레임워크", "framework", "frameworks"],
  ["검색", "search", "retrieval", "rag", "리트리벌"],
  ["분석", "애널리틱스", "analytics", "analysis"],
  ["시계열", "timeseries", "time-series"],
  ["특성", "피처", "특성공학", "feature", "features", "feature-engineering"],
  ["자바", "java", "jvm", "코틀린", "kotlin"],
  ["스프링", "spring", "springboot", "부트", "boot"],
  ["파이썬", "python"],
  ["아키텍처", "architecture", "설계", "design"],
  ["보안", "security", "취약점", "vulnerability", "cve"],
  ["성능", "performance", "throughput", "latency"],
  ["엘엘엠", "llm", "llms", "언어모델", "language-model", "gpt", "claude", "gemini", "라마", "llama", "grok"],
  ["임베딩", "embedding", "embeddings", "벡터", "vector"],
  ["배포", "deployment", "deploy", "mlops", "프로덕션", "production"],
  ["분류", "classification", "classifier", "회귀", "regression"],
];

function tokenize(s) {
  return (String(s || "").toLowerCase().match(/[a-z0-9]+|[가-힣]+/g) || []).filter((t) => t.length >= 2);
}

// Expand a query token to related terms: exact group membership plus substring
// overlap so Korean compounds ("예측모델") reach their parts (예측 + 모델).
function expandTerm(token) {
  const out = new Set([token]);
  for (const group of SYNONYMS) {
    if (group.some((g) => token.includes(g) || g.includes(token))) group.forEach((t) => out.add(t));
  }
  return out;
}

// AND across query tokens; a token is satisfied if it (or a synonym) appears in
// text. Returns a relevance score for ranking, or match=false to filter out.
function searchMatch(query, text) {
  const tokens = tokenize(query);
  if (!tokens.length) return { match: true, score: 0 };
  const t = String(text || "").toLowerCase();
  let score = 0;
  for (const tok of tokens) {
    let hit = false;
    for (const term of expandTerm(tok)) if (t.includes(term)) { hit = true; score++; }
    if (!hit) return { match: false, score: 0 };
  }
  return { match: true, score };
}

// One digest highlight: category badge + title (links to the article) + summary.
function digestItem(h) {
  const short = h.summary || h.note || "";
  const li = el("li", "digest-item");
  let html =
    `<div class="digest-head">` +
    `<span class="badge cat-${escapeHTML(h.category)}">${escapeHTML(h.category)}</span> ` +
    `<a href="${escapeHTML(h.link)}" target="_blank" rel="noopener">${escapeHTML(h.title)}</a>` +
    `</div>`;
  if (short) html += `<p class="digest-item-summary">${escapeHTML(short)}</p>`;
  if (h.detail) {
    html +=
      `<details class="digest-detail">` +
      `<summary>자세히</summary>` +
      `<div class="digest-detail-body">${escapeHTML(h.detail)}</div>` +
      `</details>`;
  }
  li.innerHTML = html;
  return li;
}

function digestList(highlights) {
  const ul = el("ul", "digest-list");
  for (const h of highlights || []) ul.appendChild(digestItem(h));
  return ul;
}

function renderDigest(data) {
  const section = document.getElementById("digest");
  const body = document.getElementById("digest-body");
  const highlights = (data && data.highlights) || [];
  if (!data || (!data.summary && !highlights.length)) {
    section.hidden = true; // hide until a digest exists
    return;
  }
  if (data.summary) body.appendChild(el("p", "digest-summary", escapeHTML(data.summary)));
  if (highlights.length) body.appendChild(digestList(highlights));
  if (data.updated) {
    document.getElementById("digest-updated").textContent =
      "갱신: " + fmtDate(data.updated, KST_FULL) + " KST";
  }
}

// "last run time" = when the routine last ran (data/digest-status.json.checked_at),
// shown at the top. All times KST. A stale value means the routine stopped running.
function renderLastRun(status) {
  if (!status || !status.checked_at) return;
  const note =
    status.result === "no-new-items" ? " (새 항목 없음)" :
    status.result === "already-today" ? " (오늘 이미 갱신됨)" : "";
  document.getElementById("last-run").textContent =
    "last run time: " + fmtDate(status.checked_at, KST_FULL) + " KST" + note;
}

// Flatten a whole day's digest into one searchable string (date + summary + every
// highlight's category/title/summary/detail), so a query hits any part of it.
function digestSearchText(d) {
  const parts = [d.date, d.summary];
  for (const h of d.highlights || []) parts.push(h.category, h.title, h.summary, h.detail);
  return parts.filter(Boolean).join(" ");
}

function archiveItem(d, open) {
  const det = el("details", "archive-item");
  if (open) det.open = true;
  const summary = el("summary");
  summary.innerHTML =
    `<span class="archive-date">${escapeHTML(d.date || "")}</span>` +
    (d.summary ? ` <span class="archive-summary">${escapeHTML(d.summary)}</span>` : "");
  det.appendChild(summary);
  det.appendChild(digestList(d.highlights));
  return det;
}

function renderArchive(data) {
  const wrap = document.getElementById("archive-list");
  const note = document.getElementById("archive-search-note");
  const input = document.getElementById("archive-search");
  const digests = (data && data.digests) || [];
  if (!digests.length) {
    wrap.appendChild(el("p", "empty", "아직 보관된 다이제스트가 없습니다. 매일 갱신되면 이전 다이제스트가 여기 쌓입니다."));
    return;
  }
  const indexed = digests.map((d) => ({ d, text: digestSearchText(d) }));

  function draw(query) {
    const q = (query || "").trim();
    wrap.innerHTML = "";
    let rows;
    if (!q) {
      rows = indexed;
      if (note) note.hidden = true;
    } else {
      rows = indexed
        .map((x) => ({ x, r: searchMatch(q, x.text) }))
        .filter((o) => o.r.match)
        .sort((a, b) => b.r.score - a.r.score)
        .map((o) => o.x);
      if (note) { note.hidden = false; note.textContent = `"${q}" 검색 결과 ${rows.length}건`; }
    }
    if (!rows.length) {
      wrap.appendChild(el("p", "empty", "검색 결과가 없습니다. 다른 키워드로 시도해 보세요."));
      return;
    }
    for (const { d } of rows) wrap.appendChild(archiveItem(d, Boolean(q)));
  }

  if (input) input.addEventListener("input", () => draw(input.value));
  draw("");
}

const NEWS_PAGE = 24; // cards per "더 보기" step — rendering all 480+ at once is wasteful

function newsCard(it) {
  const card = el("article", "card");
  card.innerHTML =
    `<div class="card-top">` +
    `<span class="badge cat-${escapeHTML(it.category)}">${escapeHTML(it.category)}</span>` +
    `<span class="src">${escapeHTML(it.source)}</span>` +
    `<time>${fmtDate(it.published)}</time>` +
    `</div>` +
    `<h3><a href="${escapeHTML(it.link)}" target="_blank" rel="noopener">${escapeHTML(it.title)}</a></h3>` +
    (it.summary ? `<p>${escapeHTML(it.summary)}</p>` : "");
  return card;
}

function renderNews(data) {
  const list = document.getElementById("news-list");
  const filterBar = document.getElementById("filters");
  const items = (data && data.items) || [];
  if (!items.length) {
    list.appendChild(el("p", "empty", "뉴스를 불러오지 못했습니다. 잠시 후 다시 시도하세요."));
    return;
  }

  const counts = { "전체": items.length };
  for (const i of items) counts[i.category] = (counts[i.category] || 0) + 1;
  const categories = ["전체", ...new Set(items.map((i) => i.category))];
  let active = "전체";
  let query = "";
  let limit = NEWS_PAGE;
  const searchInput = document.getElementById("news-search");

  function draw() {
    const shown = items.filter(
      (i) =>
        (active === "전체" || i.category === active) &&
        searchMatch(query, `${i.title} ${i.summary || ""} ${i.source} ${i.category}`).match
    );
    list.innerHTML = "";
    if (!shown.length) {
      list.appendChild(el("p", "empty", "검색 결과가 없습니다. 다른 키워드나 카테고리를 시도해 보세요."));
      return;
    }
    for (const it of shown.slice(0, limit)) list.appendChild(newsCard(it));
    if (shown.length > limit) {
      const more = el("button", "more", `더 보기 <span class="more-n">+${shown.length - limit}</span>`);
      more.addEventListener("click", () => { limit += NEWS_PAGE; draw(); });
      list.appendChild(more);
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => { query = searchInput.value; limit = NEWS_PAGE; draw(); });
  }

  filterBar.innerHTML = "";
  const buttons = categories.map((c) => {
    const btn = el("button", "filter" + (c === active ? " on" : ""));
    btn.setAttribute("aria-pressed", String(c === active));
    btn.innerHTML = `${escapeHTML(c)} <span class="filter-n">${counts[c]}</span>`;
    btn.addEventListener("click", () => {
      active = c;
      limit = NEWS_PAGE;
      buttons.forEach((b, i) => {
        const on = categories[i] === c;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", String(on));
      });
      draw();
    });
    filterBar.appendChild(btn);
    return btn;
  });
  draw();
}

// Which RSS sources each category pulls from — generated from FEEDS by fetch_news.py.
function renderSources(data) {
  const wrap = document.getElementById("sources-list");
  const cats = (data && data.categories) || [];
  if (!cats.length) {
    wrap.appendChild(el("p", "empty", "소스 정보를 불러오지 못했습니다."));
    return;
  }
  for (const c of cats) {
    const block = el("div", "source-cat");
    block.innerHTML =
      `<div class="source-cat-head">` +
      `<span class="badge cat-${escapeHTML(c.category)}">${escapeHTML(c.category)}</span>` +
      `<span class="source-count">${(c.sources || []).length}개 소스</span>` +
      `</div>`;
    const ul = el("ul", "source-links");
    for (const s of c.sources || []) {
      const li = el("li");
      li.innerHTML = `<a href="${escapeHTML(s.url)}" target="_blank" rel="noopener">${escapeHTML(s.name)}</a>`;
      ul.appendChild(li);
    }
    block.appendChild(ul);
    wrap.appendChild(block);
  }
}

(async function init() {
  const [news, digest, archive, status, sources] = await Promise.all([
    loadJSON("data/news.json"),
    loadJSON("data/digest.json"),
    loadJSON("data/archive.json"),
    loadJSON("data/digest-status.json"),
    loadJSON("data/sources.json"),
  ]);
  renderDigest(digest);
  renderLastRun(status);
  renderNews(news);
  renderArchive(archive);
  renderSources(sources);
  if (news && news.updated) {
    document.getElementById("updated").textContent =
      "뉴스 갱신: " + fmtDate(news.updated, KST_FULL) + " KST";
  }
})();
