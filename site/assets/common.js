// 공통: 헤더(탭)·푸터 렌더링과 DOM 헬퍼. innerHTML을 쓰지 않고 textContent로만 데이터를 넣는다.
(function () {
  "use strict";

  // 배포 직후 브라우저·CDN 에 남은 예전 HTML 로 열렸으면 한 번만 새로고침한다.
  // (HTML 이 불러온 이 스크립트의 ?v= 값과 서버의 version.json 을 비교)
  const myVer = (() => { try { return new URL(document.currentScript.src).searchParams.get("v"); } catch (e) { return null; } })();

  const body = document.body;
  const root = body.dataset.root || "./";       // 페이지 깊이에 따른 상대 경로 (예: "../")
  const current = body.dataset.tab || "home";

  const TABS = [
    { id: "home", label: "홈", href: "" },
    { id: "security", label: "보안·인프라", href: "security/" },
    { id: "market", label: "증시", href: "market/" },
    { id: "study", label: "학습", href: "study/" },
    { id: "about", label: "소개", href: "about/" },
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
    // data-nav="none" 인 페이지(소개)는 탭을 그리지 않는다.
    // 포트폴리오로 링크를 보냈을 때 증시 같은 다른 탭이 함께 보이지 않도록.
    const bare = body.dataset.nav === "none";
    const nav = bare ? null : h("nav", { class: "tabs", "aria-label": "탭" },
      TABS.map(t => h("a", {
        href: root + t.href,
        class: t.id === current ? "active" : null,
        "aria-current": t.id === current ? "page" : null,
        text: t.label,
      })));
    const brand = bare
      ? h("span", { class: "brand", text: "toriyong" })
      : h("a", { class: "brand", href: root, text: "toriyong" });
    const header = h("header", { class: "site-header" },
      h("div", { class: "wrap" }, [brand, nav, renderThemeSwitch()]));
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

  // 하위 메뉴: body 의 data-sub 가 있으면 해당 탭의 하위 페이지 메뉴를 헤더 아래에 그린다
  const SUBNAV = {
    market: [
      { id: "ipo", label: "공모주", href: "market/" },
      { id: "results", label: "성적표", href: "market/results/" },
      { id: "watchlist", label: "관심종목", href: "market/watchlist/" },
    ],
    study: [
      { id: "exam", label: "자격증", href: "study/" },
      { id: "notes", label: "기술 노트", href: "study/notes/" },
    ],
  };
  function renderSubnav() {
    const items = SUBNAV[current];
    const sub = body.dataset.sub;
    if (!items || !sub) return;
    const nav = h("nav", { class: "subnav", "aria-label": "하위 메뉴" }, h("div", { class: "wrap" },
      items.map(t => h("a", {
        href: root + t.href,
        class: t.id === sub ? "active" : null,
        "aria-current": t.id === sub ? "page" : null,
        text: t.label,
      }))));
    document.querySelector(".site-header").after(nav);
  }

  function renderFooter() {
    // 소개 페이지는 투자 관련 고지가 어울리지 않으므로 푸터를 두지 않는다.
    if (body.dataset.nav === "none") return;
    const footer = h("footer", { class: "site-footer" }, h("div", { class: "wrap" }, [
      h("p", { text: "이 사이트는 공개 데이터를 정리해 보여 주는 정보 사이트이며, 투자 권유나 매매 추천을 하지 않습니다. 투자 판단과 책임은 본인에게 있습니다." }),
      h("p", { text: "데이터 출처: 금융감독원 OpenDART, 한국거래소 KIND, 금융위원회 주식시세정보(공공데이터포털), CISA KEV, endoflife.date, 각 언론사·기관 RSS(제목과 링크만 표시). 원문을 반드시 확인하세요." }),
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
  if (myVer) {
    fetch(root + "version.json?t=" + Date.now(), { cache: "no-store" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => {
        if (!j || !j.v || j.v === myVer) return;
        let tried = null;
        try { tried = sessionStorage.getItem("reloaded-for"); sessionStorage.setItem("reloaded-for", j.v); } catch (e) { return; }
        if (tried !== j.v) location.reload();
      })
      .catch(() => {});
  }

  renderHeader();
  renderSubnav();
  renderFooter();
})();
