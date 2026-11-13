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
      h("div", { class: "wrap" }, [h("a", { class: "brand", href: root, text: "toriyong" }), nav, renderThemeSwitch()]));
    body.prepend(header);
  }

  // 밝게 / 어둡게 / 시스템 전환 버튼 (theme.js 가 먼저 로드되어 있어야 함)
  function renderThemeSwitch() {
    if (!window.Theme) return null;
    // 아이콘은 글꼴에 따라 깨지지 않도록 SVG로 그린다 (24x24 기준 path)
    const ICONS = {
      light: ["M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z",
        "M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"],
      dark: ["M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"],
      system: ["M3 4h18v12H3z", "M8 20h8M12 16v4"],
    };
    const svgIcon = mode => {
      const NS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(NS, "svg");
      for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: 14, height: 14, fill: "none",
        stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", class: "ico", "aria-hidden": "true" })) {
        svg.setAttribute(k, v);
      }
      for (const d of ICONS[mode]) {
        const path = document.createElementNS(NS, "path");
        path.setAttribute("d", d);
        svg.append(path);
      }
      return svg;
    };
    const OPTIONS = [
      { mode: "light", label: "밝게" },
      { mode: "dark", label: "어둡게" },
      { mode: "system", label: "시스템" },
    ];
    const group = h("div", { class: "theme-switch", role: "group", "aria-label": "화면 테마" });
    const buttons = OPTIONS.map(o => h("button", {
      type: "button",
      title: `${o.label} 모드`,
      "aria-label": `${o.label} 모드`,
      onclick: () => window.Theme.set(o.mode),
    }, [svgIcon(o.mode), h("span", { class: "lbl", text: o.label })]));
    const sync = () => {
      const cur = window.Theme.get();
      buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(OPTIONS[i].mode === cur)));
    };
    group.append(...buttons);
    document.addEventListener("themechange", sync);
    sync();
    return group;
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
