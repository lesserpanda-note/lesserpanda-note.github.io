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

function renderArchive(data) {
  const wrap = document.getElementById("archive-list");
  const digests = (data && data.digests) || [];
  if (!digests.length) {
    wrap.appendChild(el("p", "empty", "아직 보관된 다이제스트가 없습니다. 매일 갱신되면 이전 다이제스트가 여기 쌓입니다."));
    return;
  }
  for (const d of digests) {
    const det = el("details", "archive-item");
    const summary = el("summary");
    summary.innerHTML =
      `<span class="archive-date">${escapeHTML(d.date || "")}</span>` +
      (d.summary ? ` <span class="archive-summary">${escapeHTML(d.summary)}</span>` : "");
    det.appendChild(summary);
    det.appendChild(digestList(d.highlights));
    wrap.appendChild(det);
  }
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
  let limit = NEWS_PAGE;

  function draw() {
    const shown = items.filter((i) => active === "전체" || i.category === active);
    list.innerHTML = "";
    for (const it of shown.slice(0, limit)) list.appendChild(newsCard(it));
    if (shown.length > limit) {
      const more = el("button", "more", `더 보기 <span class="more-n">+${shown.length - limit}</span>`);
      more.addEventListener("click", () => { limit += NEWS_PAGE; draw(); });
      list.appendChild(more);
    }
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

(async function init() {
  const [news, digest, archive, status] = await Promise.all([
    loadJSON("data/news.json"),
    loadJSON("data/digest.json"),
    loadJSON("data/archive.json"),
    loadJSON("data/digest-status.json"),
  ]);
  renderDigest(digest);
  renderLastRun(status);
  renderNews(news);
  renderArchive(archive);
  if (news && news.updated) {
    document.getElementById("updated").textContent =
      "뉴스 갱신: " + fmtDate(news.updated, KST_FULL) + " KST";
  }
})();
