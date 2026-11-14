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

  // 아주 작은 마크다운 → DOM 변환기 (innerHTML 을 쓰지 않는다)
  function inline(parent, text) {
    // `코드`, **굵게**, [글](주소) 만 처리
    const re = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.append(text.slice(last, m.index));
      const t = m[0];
      if (t.startsWith("`")) parent.append(h("code", { text: t.slice(1, -1) }));
      else if (t.startsWith("**")) parent.append(h("strong", { text: t.slice(2, -2) }));
      else {
        const i = t.indexOf("](");
        parent.append(h("a", { href: t.slice(i + 2, -1), target: "_blank", rel: "noopener noreferrer", text: t.slice(1, i) }));
      }
      last = re.lastIndex;
    }
    if (last < text.length) parent.append(text.slice(last));
    return parent;
  }

  function markdown(src) {
    const out = [];
    const lines = (src || "").split("\n");
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^```/.test(line)) {                       // 코드 블록
        const buf = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
        i++;
        out.push(h("pre", null, h("code", { text: buf.join("\n") })));
        continue;
      }
      const hd = line.match(/^(#{2,4})\s+(.*)$/);   // 제목
      if (hd) { out.push(inline(h("h" + hd[1].length, { class: "nt-h" }), hd[2])); i++; continue; }
      if (/^\s*[-*]\s+/.test(line)) {               // 목록
        const items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
        out.push(h("ul", { class: "points" }, items.map(t => inline(h("li"), t))));
        continue;
      }
      if (/^\s*\d+\.\s+/.test(line)) {             // 번호 목록
        const items = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s+/, ""));
        out.push(h("ol", { class: "points" }, items.map(t => inline(h("li"), t))));
        continue;
      }
      if (/^\s*\|/.test(line)) {                    // 표
        const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
        const cells = rows.filter(r => !/^\s*\|[\s|:-]+\|\s*$/.test(r))
          .map(r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim()));
        if (cells.length) {
          const head = cells.shift();
          out.push(h("table", { class: "nt-table" }, [
            h("thead", null, h("tr", null, head.map(c => inline(h("th"), c)))),
            h("tbody", null, cells.map(r => h("tr", null, r.map(c => inline(h("td"), c))))),
          ]));
        }
        continue;
      }
      if (!line.trim()) { i++; continue; }
      const buf = [line];                            // 문단
      i++;
      while (i < lines.length && lines[i].trim() && !/^(#{2,4}\s|```|\s*[-*]\s|\s*\d+\.\s|\s*\|)/.test(lines[i])) buf.push(lines[i++]);
      out.push(inline(h("p", { class: "nt-p" }), buf.join(" ")));
    }
    return out;
  }

  let data = { topics: [], notes: [] };
  try {
    data = await loadJson("data.json");
  } catch (e) { /* 아직 없음 — 뼈대만 */ }

  const notes = (data.notes || []).map(n => ({ ...n, k: clean(`${n.title} ${n.summary || ""}`), i: initials(`${n.title} ${n.summary || ""}`) }));
  const topics = data.topics || [];

  // ---------- 글 한 편 보기 (?n=<id>)
  const want = new URLSearchParams(location.search).get("n");
  const one = want && notes.find(n => n.id === want);
  if (one) {
    document.title = `${one.title} · 기술 노트`;
    document.querySelector("h1").textContent = one.title;
    document.querySelector(".lead").textContent = [one.topic_name, one.updated].filter(Boolean).join(" · ");
    document.querySelectorAll(".banner, .panel").forEach(el => el.remove());
    document.querySelector(".wrap").append(
      h("article", { class: "panel nt-body" }, markdown(one.body || "본문이 없습니다.")),
      h("p", { class: "meta" }, h("a", { href: "./", text: "← 기술 노트 목록" })));
    return;
  }

  // ---------- 주제
  $("nt-topics").replaceChildren(...(topics.length ? topics : [{ id: "", name: "주제가 아직 없습니다", desc: "" }]).map(t => {
    const mine = notes.filter(n => n.topic === t.id);
    return h("div", { class: "pf-skill-row" }, [
      h("div", { class: "pf-skill-group", text: t.name }),
      h("div", null, [
        t.desc ? h("div", { class: "meta", text: t.desc }) : null,
        mine.length
          ? h("ul", { class: "plain" }, mine.map(n => h("li", null, h("a", { href: `?n=${encodeURIComponent(n.id)}`, text: n.title }))))
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
