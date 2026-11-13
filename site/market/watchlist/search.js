// 증시 > 관심종목: 종목 검색(이름·초성·종목코드) + 별표 즐겨찾기(이 브라우저에 저장)
(function () {
  "use strict";
  const { h, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);
  const ISSUE = "https://github.com/toriyong/toriyong.github.io/issues/new";
  const FAV = "market:fav";
  const CHO = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
  const MAX = 20;

  const store = {
    get() { try { return JSON.parse(localStorage.getItem(FAV) || "[]"); } catch (e) { return []; } },
    set(v) { try { localStorage.setItem(FAV, JSON.stringify(v)); } catch (e) { /* noop */ } },
  };

  // 한글 이름 → 초성 문자열 ("삼성전자" → "ㅅㅅㅈㅈ"). 한글이 아니면 그대로 둔다.
  function initials(s) {
    let out = "";
    for (const ch of s) {
      const c = ch.charCodeAt(0);
      out += (c >= 0xac00 && c <= 0xd7a3) ? CHO[Math.floor((c - 0xac00) / 588)] : ch;
    }
    return out;
  }
  const isChoOnly = s => s.length > 0 && [...s].every(c => CHO.indexOf(c) >= 0);
  const clean = s => (s || "").replace(/\s+/g, "").toLowerCase();

  const box = $("stock-search");
  if (!box) return;
  const input = $("q");
  const list = $("sr");
  const note = $("sr-note");
  const favList = $("fav-list");
  const favNote = $("fav-note");

  let items = null;     // [{c, n, m, i, k}]
  let loading = null;
  let favs = store.get();
  const isFav = code => favs.some(f => f.c === code);

  function load() {
    if (loading) return loading;
    loading = loadJson("../stocks.json").then(d => {
      items = (d.stocks || []).map(x => ({ ...x, i: initials(x.n), k: clean(x.n) }));
      note.textContent = `${d.count || items.length}개 종목에서 검색합니다.`;
      return items;
    }).catch(() => {
      items = [];
      note.textContent = "종목 목록을 아직 내려받지 못했습니다. 다음 자동 수집 후 검색할 수 있습니다.";
      return items;
    });
    return loading;
  }

  function search(qRaw) {
    const q = clean(qRaw);
    if (!q || !items) return [];
    const cho = isChoOnly(q);
    const hits = [];
    for (const x of items) {
      let rank = -1;
      if (/^\d+$/.test(q)) {                       // 종목코드
        if (x.c.startsWith(q)) rank = x.c === q ? 0 : 2;
      } else if (cho) {                            // 초성 (ㅅㅅㅈㅈ)
        if (x.i.startsWith(q)) rank = 1;
        else if (x.i.includes(q)) rank = 3;
      } else {                                     // 이름
        if (x.k === q) rank = 0;
        else if (x.k.startsWith(q)) rank = 1;
        else if (x.k.includes(q)) rank = 3;
        else if (x.i.startsWith(q)) rank = 4;      // "삼ㅈㅈ" 같은 혼합 입력
      }
      if (rank >= 0) hits.push({ x, rank });
    }
    hits.sort((a, b) => a.rank - b.rank || a.x.n.length - b.x.n.length || a.x.n.localeCompare(b.x.n));
    return hits.slice(0, MAX).map(v => v.x);
  }

  function issueHref(action, x) {
    const p = new URLSearchParams({ template: "watchlist.yml", action, name: x.n, code: x.c });
    return `${ISSUE}?${p.toString()}`;
  }

  function toggleFav(x) {
    favs = isFav(x.c) ? favs.filter(f => f.c !== x.c) : favs.concat([{ c: x.c, n: x.n, m: x.m }]);
    favs.sort((a, b) => a.n.localeCompare(b.n));
    store.set(favs);
    renderFavs();
    render(search(input.value), clean(input.value));
  }

  function starBtn(x) {
    const on = isFav(x.c);
    return h("button", {
      type: "button", class: `star${on ? " on" : ""}`,
      title: on ? `${x.n} 즐겨찾기 해제` : `${x.n} 즐겨찾기 추가`,
      "aria-label": on ? `${x.n} 즐겨찾기 해제` : `${x.n} 즐겨찾기 추가`,
      "aria-pressed": String(on),
      onclick: () => toggleFav(x),
      text: on ? "★" : "☆",
    });
  }

  function row(x, cls) {
    return h("li", { class: cls }, [
      starBtn(x),
      h("div", { class: "sr-main" }, [
        h("strong", { class: "sr-name", text: x.n }),
        h("span", { class: "sr-code" }, [x.c, h("span", { class: "meta", text: ` ${x.m}` })]),
      ]),
      h("a", {
        class: "sr-add", href: issueHref("종목 추가", x), target: "_blank", rel: "noopener noreferrer",
        title: `${x.n} 을 GitHub 에 등록해 뉴스·공시·목표가를 받습니다`, text: "등록 ↗",
      }),
    ]);
  }

  function render(rows, q) {
    if (!q) { list.replaceChildren(); return; }
    if (!rows.length) {
      list.replaceChildren(h("li", { class: "empty", text: "검색 결과가 없습니다. 종목명이나 종목코드로 다시 찾아보세요." }));
      return;
    }
    list.replaceChildren(...rows.map(x => row(x, "sr-item")));
  }

  function renderFavs() {
    if (!favs.length) {
      favList.replaceChildren(h("li", { class: "empty", text: "아직 즐겨찾기가 없습니다. 아래에서 종목을 찾아 ☆ 를 누르세요." }));
      favNote.textContent = "이 브라우저에만 저장됩니다.";
      return;
    }
    favList.replaceChildren(...favs.map(x => row(x, "sr-item fav")));
    favNote.textContent = `${favs.length}개 · 이 브라우저에만 저장됩니다. 뉴스·공시·목표가까지 받으려면 '등록'을 누르세요.`;
  }

  let timer = 0;
  input.addEventListener("input", () => {
    const q = input.value;
    clearTimeout(timer);
    timer = setTimeout(() => { load().then(() => render(search(q), clean(q))); }, 80);
  });
  input.addEventListener("focus", load, { once: true });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") { input.value = ""; render([], ""); }
  });
  $("q-clear").addEventListener("click", () => { input.value = ""; render([], ""); input.focus(); });
  renderFavs();
})();
