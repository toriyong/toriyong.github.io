// 보안·인프라 페이지
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);

  const SEV = {
    critical: { label: "Critical", cls: "sev-critical" },
    high: { label: "High", cls: "sev-high" },
    medium: { label: "Medium", cls: "sev-medium" },
    info: { label: "Info", cls: "sev-info" },
  };
  const sevBadge = s => h("span", { class: `badge ${SEV[s]?.cls || ""}`, text: SEV[s]?.label || s });
  const catTag = c => h("span", { class: "tag", text: c });

  // '3시간 전' 형식
  function ago(iso) {
    if (!iso) return "";
    const diff = (Date.now() - new Date(iso).getTime()) / 60000;
    if (diff < 60) return `${Math.max(1, Math.round(diff))}분 전`;
    if (diff < 60 * 24) return `${Math.round(diff / 60)}시간 전`;
    return `${Math.round(diff / 60 / 24)}일 전`;
  }
  const emptyRow = (cols, text) => h("tr", null, h("td", { colspan: cols, class: "empty", text }));

  let data;
  try {
    data = await loadJson("data/secinfra.json");
  } catch (e) {
    $("stats").replaceChildren(h("span", { class: "meta", text: "아직 수집된 데이터가 없습니다. 첫 배포 후 자동 수집이 끝나면 표시됩니다." }));
    return;
  }

  // ---------- 배너 · 기준 시각
  if (data.sample) $("banner-sample").classList.remove("hidden");
  if ((data.errors || []).length || (data.stale_sections || []).length) {
    const b = $("banner-error");
    b.textContent = `일부 출처 수집에 실패했습니다 (${(data.errors || []).length}건). 실패한 항목은 직전 데이터 또는 빈 값으로 표시됩니다.`;
    b.title = (data.errors || []).join("\n");
    b.classList.remove("hidden");
  }
  $("updated").textContent = `기준 시각 ${fmt.stamp(data.updated_at)} (KST)`;

  const news = data.news || [];
  const s = data.summary || {};
  const kev = data.kev || {};
  const patches = data.patches || [];
  const eol = data.eol || [];
  const eolWarn = eol.flatMap(p => p.cycles.filter(c => c.status === "warn").map(c => ({ p, c })));

  // ---------- 1. 요약 타일
  const tile = (label, value, note, tone, href) => h("a", { class: `stat-tile ${tone || ""}`, href }, [
    h("span", { class: "stat-label", text: label }),
    h("span", { class: "stat-value", text: value }),
    h("span", { class: "stat-note", text: note }),
  ]);
  const ms = patches.find(p => p.name.startsWith("Microsoft"));
  $("stats").replaceChildren(
    tile("Critical 이슈", s.critical ?? 0, `High ${s.high ?? 0}건 · 기사 ${s.news_total ?? 0}건(7일)`, s.critical ? "tone-bad" : "", "#top-issues"),
    tile("실제 악용 취약점", s.kev_recent ?? 0, `최근 ${kev.days || 14}일 신규 · 랜섬웨어 연관 ${s.kev_ransomware ?? 0}건`, s.kev_recent ? "tone-warn" : "", "#kev"),
    tile("다음 MS 패치", ms ? `D-${ms.d_day}` : "–", ms ? `${fmt.md(ms.date)} (미국) · ${ms.kst_note.replace(/^한국시간 \d{4}-/, "").replace(" 새벽 공개", " 새벽")}` : "", "", "#patch"),
    tile("지원 종료 임박", eolWarn.length, eolWarn.length ? eolWarn.slice(0, 2).map(x => `${x.p.name} ${x.c.cycle}`).join(", ") : "180일 이내 없음", eolWarn.length ? "tone-warn" : "", "#infra"),
  );

  // ---------- 2. 주요 이슈
  const byId = Object.fromEntries(news.map(n => [n.id, n]));
  const top = (data.top || []).map(id => byId[id]).filter(Boolean);
  $("top-list").replaceChildren(...(top.length ? top.map(n => h("li", { class: "top-item" }, [
    h("div", { class: "top-meta" }, [sevBadge(n.severity), ...n.categories.slice(0, 3).map(catTag),
      h("span", { class: "src", text: `${n.source} · ${ago(n.published)}` })]),
    h("a", { class: "top-title", href: n.link, target: "_blank", rel: "noopener noreferrer", text: n.title }),
  ])) : [h("li", { class: "empty", text: "최근 48시간 내 기사가 없습니다" })]));

  // ---------- 3. 보안 뉴스 (필터)
  const state = { region: "all", sev: "all", cat: "all", limit: 20 };
  const cats = Object.keys(s.by_category || {});
  const FILTERS = {
    "f-region": ["region", [["all", "전체"], ["kr", "국내"], ["global", "해외"]]],
    "f-sev": ["sev", [["all", "모든 심각도"], ["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["info", "Info"]]],
    "f-cat": ["cat", [["all", "모든 카테고리"], ...cats.map(c => [c, `${c} ${s.by_category[c] || 0}`])]],
  };
  function renderFilters() {
    for (const [elId, [key, opts]] of Object.entries(FILTERS)) {
      $(elId).replaceChildren(...opts.map(([v, label]) => h("button", {
        type: "button", class: state[key] === v ? "on" : null, text: label, "aria-pressed": String(state[key] === v),
        onclick: () => { state[key] = v; state.limit = 20; renderFilters(); renderNews(); },
      })));
    }
  }
  function renderNews() {
    const rows = news.filter(n => (state.region === "all" || n.region === state.region)
      && (state.sev === "all" || n.severity === state.sev)
      && (state.cat === "all" || n.categories.includes(state.cat)));
    $("news-count").textContent = `${rows.length}건`;
    $("news-list").replaceChildren(...(rows.length ? rows.slice(0, state.limit).map(n => h("li", { class: "news-item" }, [
      h("div", { class: "news-main" }, [
        h("a", { href: n.link, target: "_blank", rel: "noopener noreferrer", text: n.title }),
        h("div", { class: "news-sub" }, [sevBadge(n.severity), ...n.categories.slice(0, 3).map(catTag),
          h("span", { class: "src", text: `${n.source} · ${ago(n.published)}` })]),
      ]),
    ])) : [h("li", { class: "empty", text: "조건에 맞는 기사가 없습니다" })]));
    $("news-more").classList.toggle("hidden", rows.length <= state.limit);
  }
  $("news-more").addEventListener("click", () => { state.limit += 20; renderNews(); });
  renderFilters();
  renderNews();

  // ---------- 4. 위협 동향 (막대)
  const entries = Object.entries(s.by_category || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  $("bars").replaceChildren(...entries.map(([c, v]) => {
    const fill = h("span", { class: "bar-fill" });
    fill.style.width = `${(v / max) * 100}%`;          // CSSOM 설정은 CSP(style-src 'self')에 막히지 않음
    return h("li", { class: "bar-row" }, [
      h("button", { type: "button", class: "bar-label", text: c, title: `${c} 기사만 보기`,
        onclick: () => { state.cat = c; state.limit = 20; renderFilters(); renderNews(); location.hash = "news"; } }),
      h("span", { class: "bar-track" }, fill),
      h("span", { class: "bar-value", text: v }),
    ]);
  }));

  // ---------- 5. KEV
  $("kev-meta").textContent = kev.total ? `카탈로그 전체 ${fmt.num(kev.total)}건 · 버전 ${kev.catalog_version || "–"}` : "";
  const kevRows = kev.recent || [];
  $("kev-rows").replaceChildren(...(kevRows.length ? kevRows.map(v => h("tr", null, [
    h("td", { "data-label": "추가일", text: fmt.md(v.added) }),
    h("td", { "data-label": "CVE", class: "card-title" }, h("a", { href: v.url, target: "_blank", rel: "noopener noreferrer", text: v.cve })),
    h("td", { "data-label": "제품", text: `${v.vendor || ""} ${v.product || ""}`.trim() }),
    h("td", { "data-label": "취약점", class: "wrap-cell", text: v.name || "–" }),
    h("td", { "data-label": "조치 기한", text: v.due || "–" }),
    h("td", { "data-label": "랜섬웨어" }, v.ransomware ? h("span", { class: "badge sev-critical", text: "악용 확인" }) : "–"),
  ])) : [emptyRow(6, `최근 ${kev.days || 14}일 신규 항목이 없습니다`)]));

  // ---------- 6. 패치 일정
  $("patch-list").replaceChildren(...(patches.length ? patches.map(p => h("li", { class: "patch-item" }, [
    h("span", { class: `dday ${p.d_day <= 7 ? "soon" : ""}`, text: p.d_day <= 0 ? "D-Day" : `D-${p.d_day}` }),
    h("div", null, [
      h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer", text: p.name }),
      h("div", { class: "meta", text: `${p.date} (미국) · ${p.kst_note}` }),
    ]),
  ])) : [h("li", { class: "empty", text: "일정 정보 없음" })]));

  // ---------- 7. EOL
  const statusText = c => c.status === "ended" ? "종료됨" : c.days_left === null ? "종료일 미정" : `D-${fmt.num(c.days_left)}`;
  $("eol-grid").replaceChildren(...(eol.length ? eol.map(p => h("div", { class: "eol-card" }, [
    h("div", { class: "eol-head" }, [h("strong", { text: p.name }),
      h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer", class: "meta", text: "상세" })]),
    h("ul", null, p.cycles.length ? p.cycles.map(c => h("li", { class: `eol-row st-${c.status}` }, [
      h("span", { class: "eol-ver", text: c.cycle + (c.lts ? " LTS" : "") }),
      h("span", { class: "eol-date", text: c.eol || "–" }),
      h("span", { class: "eol-left", text: statusText(c) }),
    ])) : [h("li", { class: "meta", text: "지원 중인 버전 정보 없음" })]),
  ])) : [h("p", { class: "empty", text: "EOL 데이터 없음" })]));

  // ---------- 8. 클라우드 상태
  const inc = data.cloud?.incidents || [];
  $("incident-list").replaceChildren(...(inc.length ? inc.slice(0, 6).map(i => h("li", null, [
    h("span", { class: "tag", text: i.provider }),
    h("a", { href: i.link, target: "_blank", rel: "noopener noreferrer", text: i.title }),
    h("span", { class: "meta", text: ` · ${ago(i.published)}` }),
  ])) : [h("li", { class: "meta", text: "최근 7일 Azure 공개 장애 공지 없음" })]));
  $("status-links").replaceChildren(...(data.cloud?.links || []).map(l =>
    h("a", { class: "chip", href: l.url, target: "_blank", rel: "noopener noreferrer", text: l.name })));
})();
