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

function renderNotes(data) {
  const wrap = document.getElementById("notes");
  const items = (data && data.items) || [];
  if (!items.length) {
    wrap.appendChild(el("p", "empty", "아직 작성한 인사이트가 없습니다. <code>notes/</code>에 마크다운을 추가하세요."));
    return;
  }
  for (const n of items) {
    const det = el("details", "note");
    const tags = (n.tags || []).map((t) => `<span class="tag">#${escapeHTML(t)}</span>`).join(" ");
    const summary = el("summary");
    summary.innerHTML =
      `<span class="note-title">${escapeHTML(n.title)}</span>` +
      `<span class="note-meta">${escapeHTML(n.date)} ${tags}</span>`;
    det.appendChild(summary);
    det.appendChild(el("div", "note-body", n.html || ""));
    wrap.appendChild(det);
  }
}

function renderNews(data) {
  const list = document.getElementById("news-list");
  const filterBar = document.getElementById("filters");
  const items = (data && data.items) || [];
  if (!items.length) {
    list.appendChild(el("p", "empty", "뉴스를 불러오지 못했습니다. 잠시 후 다시 시도하세요."));
    return;
  }

  const categories = ["전체", ...new Set(items.map((i) => i.category))];
  let active = "전체";

  function draw() {
    list.innerHTML = "";
    const shown = items.filter((i) => active === "전체" || i.category === active);
    for (const it of shown) {
      const card = el("article", "card");
      card.innerHTML =
        `<div class="card-top">` +
        `<span class="badge cat-${escapeHTML(it.category)}">${escapeHTML(it.category)}</span>` +
        `<span class="src">${escapeHTML(it.source)}</span>` +
        `<time>${fmtDate(it.published)}</time>` +
        `</div>` +
        `<h3><a href="${escapeHTML(it.link)}" target="_blank" rel="noopener">${escapeHTML(it.title)}</a></h3>` +
        (it.summary ? `<p>${escapeHTML(it.summary)}</p>` : "");
      list.appendChild(card);
    }
  }

  filterBar.innerHTML = "";
  for (const c of categories) {
    const btn = el("button", "filter" + (c === active ? " on" : ""), escapeHTML(c));
    btn.addEventListener("click", () => {
      active = c;
      [...filterBar.children].forEach((x) => x.classList.toggle("on", x.textContent === c));
      draw();
    });
    filterBar.appendChild(btn);
  }
  draw();
}

(async function init() {
  const [news, notes] = await Promise.all([
    loadJSON("data/news.json"),
    loadJSON("data/notes.json"),
  ]);
  renderNotes(notes);
  renderNews(news);
  if (news && news.updated) {
    document.getElementById("updated").textContent =
      "뉴스 갱신: " + fmtDate(news.updated, KST_FULL) + " KST";
  }
})();
