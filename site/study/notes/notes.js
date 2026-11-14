// 학습 > 기술 노트: 주제 목록과 검색. 노트가 없으면 주제 뼈대만 보여 준다.
(async function () {
  "use strict";
  const { h, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);
  const CHO = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
  const initials = s => [...(s || "")].map(ch => {
    const c = ch.charCodeAt(0);
    return (c >= 0xac00 && c <= 0xd7a3) ? CHO[Math.floor((c - 0xac00) / 588)] : ch;
  }).join("");
  const clean = s => (s || "").replace(/\s+/g, "").toLowerCase();
  const isCho = s => s.length > 0 && [...s].every(c => CHO.indexOf(c) >= 0);

  let data = { topics: [], notes: [] };
  try {
    data = await loadJson("data.json");
  } catch (e) { /* 아직 없음 — 뼈대만 */ }

  const notes = (data.notes || []).map(n => ({ ...n, k: clean(`${n.title} ${n.summary || ""}`), i: initials(`${n.title} ${n.summary || ""}`) }));
  const topics = data.topics || [];

  // ---------- 주제
  $("nt-topics").replaceChildren(...(topics.length ? topics : [{ id: "", name: "주제가 아직 없습니다", desc: "" }]).map(t => {
    const mine = notes.filter(n => n.topic === t.id);
    return h("div", { class: "pf-skill-row" }, [
      h("div", { class: "pf-skill-group", text: t.name }),
      h("div", null, [
        t.desc ? h("div", { class: "meta", text: t.desc }) : null,
        mine.length
          ? h("ul", { class: "plain" }, mine.map(n => h("li", h("a", { href: `?n=${encodeURIComponent(n.id)}`, text: n.title }))))
          : h("span", { class: "meta", text: "준비 중" }),
      ]),
    ]);
  }));

  // ---------- 검색
  const q = $("nt-q"), list = $("nt-results");
  $("nt-count").textContent = notes.length ? `${notes.length}개 노트` : "노트 없음";
  if (!notes.length) return;
  q.disabled = false;
  $("nt-clear").disabled = false;

  function render(rows) {
    if (!rows.length) { list.replaceChildren(h("li", { class: "empty", text: "결과가 없습니다." })); return; }
    list.replaceChildren(...rows.slice(0, 30).map(n => h("li", { class: "sr-item" }, [
      h("div", { class: "sr-main" }, [
        h("a", { class: "sr-name", href: `?n=${encodeURIComponent(n.id)}`, text: n.title }),
        h("span", { class: "sr-code meta", text: [n.topic_name, n.updated].filter(Boolean).join(" · ") }),
      ]),
    ])));
  }
  let timer = 0;
  q.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const v = clean(q.value);
      if (!v) { list.replaceChildren(); return; }
      render(notes.filter(n => isCho(v) ? n.i.includes(v) : n.k.includes(v)));
    }, 80);
  });
  $("nt-clear").addEventListener("click", () => { q.value = ""; list.replaceChildren(); q.focus(); });
})();
