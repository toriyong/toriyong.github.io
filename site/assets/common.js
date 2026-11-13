// 공통: 헤더(탭)·푸터 렌더링과 DOM 헬퍼. innerHTML을 쓰지 않고 textContent로만 데이터를 넣는다.
(function () {
  "use strict";

  const body = document.body;
  const root = body.dataset.root || "./";       // 페이지 깊이에 따른 상대 경로 (예: "../")
  const current = body.dataset.tab || "home";

  const TABS = [
    { id: "home", label: "홈", href: "" },
    { id: "security", label: "보안", href: "security/" },
    { id: "infra", label: "인프라", href: "infra/" },
    { id: "market", label: "증시", href: "market/" },
  ];

  function h(tag, attrs, children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of [].concat(children || [])) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }

  function renderHeader() {
    const nav = h("nav", { class: "tabs", "aria-label": "탭" },
      TABS.map(t => h("a", {
        href: root + t.href,
        class: t.id === current ? "active" : null,
        "aria-current": t.id === current ? "page" : null,
        text: t.label,
      })));
    const header = h("header", { class: "site-header" },
      h("div", { class: "wrap" }, [h("a", { class: "brand", href: root, text: "toriyong" }), nav]));
    body.prepend(header);
  }

  function renderFooter() {
    const footer = h("footer", { class: "site-footer" }, h("div", { class: "wrap" }, [
      h("p", { text: "이 사이트는 공개 데이터를 정리해 보여 주는 정보 사이트이며, 투자 권유나 매매 추천을 하지 않습니다. 투자 판단과 책임은 본인에게 있습니다." }),
      h("p", { text: "데이터 출처: 금융감독원 OpenDART. 수치는 공시 기준이며 원문과 다를 수 있으니 반드시 원문 공시를 확인하세요." }),
    ]));
    body.append(footer);
  }

  const fmt = {
    num(v, digits = 0) {
      if (v === null || v === undefined || v === "") return "–";
      const n = Number(v);
      return Number.isFinite(n) ? n.toLocaleString("ko-KR", { maximumFractionDigits: digits }) : "–";
    },
    pct(v) { return v === null || v === undefined || v === "" ? "–" : fmt.num(v, 1) + "%"; },
    ratio(v) { return v === null || v === undefined || v === "" ? "–" : fmt.num(v, 1) + ":1"; },
    md(iso) {
      if (!iso) return "–";
      const [, m, d] = iso.split("-");
      return `${Number(m)}.${Number(d)}`;
    },
    period(a, b) {
      if (!a) return "–";
      return a === b || !b ? fmt.md(a) : `${fmt.md(a)} ~ ${fmt.md(b)}`;
    },
    stamp(iso) {
      if (!iso) return "–";
      return iso.replace("T", " ").slice(0, 16);
    },
  };

  // KST 기준 오늘 날짜(YYYY-MM-DD)
  function todayKst() {
    const now = new Date(Date.now() + 9 * 3600 * 1000);
    return now.toISOString().slice(0, 10);
  }

  async function loadJson(path) {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return res.json();
  }

  window.Hub = { h, fmt, todayKst, loadJson, root };
  renderHeader();
  renderFooter();
})();
