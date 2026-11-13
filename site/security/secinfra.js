// 보안·인프라 페이지
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);

  const SEV = { critical: "Critical", high: "High", medium: "Medium", info: "Info" };
  const sevBadge = s => h("span", { class: `badge sev-${s}`, text: SEV[s] || s });
  const ORG_CLS = { KISA: "org-kisa", 금융보안원: "org-fsi", CISA: "org-cisa" };
  const orgBadge = o => h("span", { class: `org ${ORG_CLS[o] || ""}`, text: o });
  const ext = (href, text, cls) => h("a", { href, target: "_blank", rel: "noopener noreferrer", class: cls, text });

  function ago(iso) {
    if (!iso) return "";
    const diff = (Date.now() - new Date(iso).getTime()) / 60000;
    if (diff < 60) return `${Math.max(1, Math.round(diff))}분 전`;
    if (diff < 60 * 24) return `${Math.round(diff / 60)}시간 전`;
    if (diff < 60 * 24 * 7) return `${Math.round(diff / 60 / 24)}일 전`;
    return iso.slice(0, 10);
  }
  const emptyLi = text => h("li", { class: "empty", text });

  let data;
  try {
    data = await loadJson("data/secinfra.json");
  } catch (e) {
    $("stats").replaceChildren(h("span", { class: "meta", text: "아직 수집된 데이터가 없습니다. 첫 배포 후 자동 수집이 끝나면 표시됩니다." }));
    return;
  }

  if (data.sample) $("banner-sample").classList.remove("hidden");
  if ((data.errors || []).length) {
    const b = $("banner-error");
    b.textContent = `일부 출처 수집에 실패했습니다 (${data.errors.length}건). 해당 항목은 직전 데이터로 표시됩니다.`;
    b.title = data.errors.join("\n");
    b.classList.remove("hidden");
  }
  $("updated").textContent = `기준 시각 ${fmt.stamp(data.updated_at)} (KST)`;

  const s = data.summary || {};
  const official = data.official || [];
  const cves = data.cves || { kr: [], global: [] };
  const media = data.media || [];
  const kev = data.kev || {};
  const patches = data.patches || [];
  const eol = data.eol || [];
  const eolWarn = eol.flatMap(p => p.cycles.filter(c => c.status === "warn").map(c => `${p.name} ${c.cycle}`));
  const ms = patches.find(p => p.name.startsWith("Microsoft"));

  // ---------- 요약
  const tile = (label, value, note, tone, href) => h("a", { class: `stat-tile ${tone || ""}`, href }, [
    h("span", { class: "stat-label", text: label }), h("span", { class: "stat-value", text: value }),
    h("span", { class: "stat-note", text: note })]);
  $("stats").replaceChildren(
    tile("공식 공지", s.official_24h ?? 0, `최근 24시간 · 30일 ${s.official ?? 0}건`, "", "#official"),
    tile("신규 CVE", (s.cve_kr ?? 0) + (s.cve_global ?? 0), `Critical ${s.cve_critical ?? 0}건 · 국내 ${s.cve_kr ?? 0} · 글로벌 ${s.cve_global ?? 0}`, s.cve_critical ? "tone-bad" : "", "#cve"),
    tile("실제 악용 취약점", s.kev_recent ?? 0, `최근 ${kev.days || 14}일 · 랜섬웨어 연관 ${s.kev_ransomware ?? 0}`, s.kev_recent ? "tone-warn" : "", "#kev"),
    tile("다음 MS 패치", ms ? `D-${ms.d_day}` : "–", ms ? `${fmt.md(ms.date)} (미국) · 한국 다음날 새벽` : "", "", "#patch"),
    tile("지원 종료 임박", eolWarn.length, eolWarn.slice(0, 2).join(", ") || "180일 이내 없음", eolWarn.length ? "tone-warn" : "", "#infra"),
  );

  // ---------- 1. 공식 공지
  const off = { org: "all", limit: 12 };
  const orgs = ["all", ...new Set(official.map(o => o.org))];
  function feedItem(o) {
    return h("li", { class: "feed-item" }, [
      h("div", { class: "feed-meta" }, [orgBadge(o.org), sevBadge(o.severity), h("span", { class: "src", text: `${o.source} · ${ago(o.published)}` })]),
      ext(o.link, o.title, "feed-title"),
      o.summary ? h("p", { class: "feed-sum", text: o.summary }) : null,
    ]);
  }
  function renderOfficial() {
    $("f-org").replaceChildren(...orgs.map(o => h("button", {
      type: "button", class: off.org === o ? "on" : null, "aria-pressed": String(off.org === o),
      text: o === "all" ? "전체" : `${o} ${official.filter(x => x.org === o).length}`,
      onclick: () => { off.org = o; off.limit = 12; renderOfficial(); } })));
    const rows = official.filter(o => off.org === "all" || o.org === off.org);
    $("official-count").textContent = `${rows.length}건`;
    $("official-list").replaceChildren(...(rows.length ? rows.slice(0, off.limit).map(feedItem) : [emptyLi("최근 30일 공지가 없습니다")]));
    $("official-more").classList.toggle("hidden", rows.length <= off.limit);
  }
  $("official-more").addEventListener("click", () => { off.limit += 12; renderOfficial(); });
  renderOfficial();

  // ---------- 2. 최근 CVE
  const CVE_TABS = [
    ["kr", "국내 (KISA)", "KISA 사이버 보안 취약점 정보 포털(KNVD)에 최근 공개된 국내 제품 취약점입니다."],
    ["global", "글로벌 Critical (NVD)", "미국 NVD에 최근 7일간 등록된 CVSS 9.0 이상 취약점입니다."],
  ];
  let cveTab = "kr";
  function renderCve() {
    $("cve-tabs").replaceChildren(...CVE_TABS.map(([id, label]) => h("button", {
      type: "button", role: "tab", class: cveTab === id ? "on" : null, "aria-selected": String(cveTab === id),
      text: `${label} ${(cves[id] || []).length}`, onclick: () => { cveTab = id; renderCve(); } })));
    $("cve-desc").textContent = CVE_TABS.find(t => t[0] === cveTab)[2];
    const rows = cves[cveTab] || [];
    $("cve-list").replaceChildren(...(rows.length ? rows.map(c => h("li", { class: "cve-item" }, [
      h("span", { class: `score sev-${c.severity}`, text: c.cvss != null ? Number(c.cvss).toFixed(1) : "–", title: "CVSS 점수" }),
      h("div", { class: "cve-main" }, [
        h("div", { class: "cve-top" }, [ext(c.link, c.id, "cve-id"),
          c.kev ? h("span", { class: "badge sev-critical", text: "실제 악용" }) : null,
          h("span", { class: "src", text: ago(c.published) })]),
        h("div", { class: "cve-title", text: c.title }),
        c.summary ? h("div", { class: "cve-sum", text: c.summary }) : null,
      ]),
    ])) : [emptyLi("최근 등록된 항목이 없습니다")]));
  }
  renderCve();

  // ---------- 3. 킬 체인 · 제로트러스트
  const fw = data.frameworks || { killchain: [], zerotrust: [] };
  const pool = [
    ...official.map(o => ({ ...o, kind: o.org })),
    ...(cves.kr || []).map(c => ({ ...c, kind: "CVE", title: `${c.id} ${c.title}` })),
    ...(cves.global || []).map(c => ({ ...c, kind: "CVE", title: `${c.id} ${c.title}` })),
    ...media.map(m => ({ ...m, kind: "보도" })),
  ];
  let active = null;
  function openDetail(type, g) {
    const key = `${type}:${g.id}`;
    if (active === key) { closeDetail(); return; }
    active = key;
    const items = pool.filter(x => (x[type] || []).includes(g.id));
    $("frame-title").textContent = `${g.name} — 관련 ${items.length}건${g.check ? ` · 점검: ${g.check}` : ""}`;
    $("frame-list").replaceChildren(...(items.length ? items.slice(0, 15).map(x => h("li", { class: "feed-item" }, [
      h("div", { class: "feed-meta" }, [h("span", { class: "tag", text: x.kind }), sevBadge(x.severity), h("span", { class: "src", text: ago(x.published) })]),
      ext(x.link, x.title, "feed-title")])) : [emptyLi("최근 관련 항목이 없습니다")]));
    $("frame-detail").classList.remove("hidden");
    document.querySelectorAll(".chain-step, .zt-tile").forEach(el => el.classList.toggle("on", el.dataset.key === key));
  }
  function closeDetail() {
    active = null;
    $("frame-detail").classList.add("hidden");
    document.querySelectorAll(".chain-step, .zt-tile").forEach(el => el.classList.remove("on"));
  }
  $("frame-close").addEventListener("click", closeDetail);
  const kc = s.killchain || {};
  $("chain").replaceChildren(...fw.killchain.map((g, i) => h("li", null,
    h("button", { type: "button", class: `chain-step ${kc[g.id] ? "has" : ""}`, "data-key": `killchain:${g.id}`, onclick: () => openDetail("killchain", g) }, [
      h("span", { class: "chain-no", text: i + 1 }), h("strong", { text: g.name }),
      h("span", { class: "chain-count", text: `${kc[g.id] || 0}건` }), h("span", { class: "chain-desc", text: g.desc })]))));
  const zt = s.zerotrust || {};
  $("zt").replaceChildren(...fw.zerotrust.map(g =>
    h("button", { type: "button", class: `zt-tile ${zt[g.id] ? "has" : ""}`, "data-key": `zerotrust:${g.id}`, onclick: () => openDetail("zerotrust", g) }, [
      h("span", { class: "zt-head" }, [h("strong", { text: g.name }), h("span", { class: "zt-count", text: zt[g.id] || 0 })]),
      h("span", { class: "zt-check", text: g.check })])));

  // ---------- 4. KEV
  $("kev-meta").textContent = kev.total ? `카탈로그 전체 ${fmt.num(kev.total)}건` : "";
  const kevRows = kev.recent || [];
  $("kev-rows").replaceChildren(...(kevRows.length ? kevRows.map(v => h("tr", null, [
    h("td", { "data-label": "추가일", text: fmt.md(v.added) }),
    h("td", { "data-label": "CVE", class: "card-title" }, ext(v.url, v.cve)),
    h("td", { "data-label": "제품", text: `${v.vendor || ""} ${v.product || ""}`.trim() }),
    h("td", { "data-label": "취약점", class: "wrap-cell", text: v.name || "–" }),
    h("td", { "data-label": "조치 기한", text: v.due || "–" }),
    h("td", { "data-label": "랜섬웨어" }, v.ransomware ? h("span", { class: "badge sev-critical", text: "악용 확인" }) : "–"),
  ])) : [h("tr", null, h("td", { colspan: 6, class: "empty", text: `최근 ${kev.days || 14}일 신규 항목이 없습니다` }))]));

  // ---------- 5. 주요 사고 보도
  $("media-list").replaceChildren(...(media.length ? media.map(m => h("li", { class: "feed-item" }, [
    h("div", { class: "feed-meta" }, [
      h("span", { class: `badge ${m.count >= 3 ? "sev-critical" : m.count === 2 ? "sev-high" : "sev-info"}`, text: `${m.count}개 매체` }),
      sevBadge(m.severity), h("span", { class: "tag", text: m.region === "kr" ? "국내" : "해외" }),
      h("span", { class: "src", text: ago(m.published) })]),
    ext(m.link, m.title, "feed-title"),
    m.summary ? h("p", { class: "feed-sum", text: m.summary }) : null,
    h("div", { class: "outlets", text: m.outlets.join(" · ") }),
  ])) : [emptyLi("최근 72시간 신뢰 매체 보도가 없습니다")]));

  // ---------- 6. 패치 · 클라우드 · EOL
  $("patch-list").replaceChildren(...(patches.length ? patches.map(p => h("li", { class: "patch-item" }, [
    h("span", { class: `dday ${p.d_day <= 7 ? "soon" : ""}`, text: p.d_day <= 0 ? "D-Day" : `D-${p.d_day}` }),
    h("div", null, [ext(p.url, p.name), h("div", { class: "meta", text: `${p.date} (미국) · ${p.kst_note}` })]),
  ])) : [emptyLi("일정 정보 없음")]));

  const inc = data.cloud?.incidents || [];
  $("incident-list").replaceChildren(...(inc.length ? inc.slice(0, 6).map(i => h("li", null, [
    h("span", { class: "tag", text: i.provider }), ext(i.link, i.title), h("span", { class: "meta", text: ` · ${ago(i.published)}` })]))
    : [h("li", { class: "meta", text: "최근 7일 Azure 공개 장애 공지 없음" })]));
  $("status-links").replaceChildren(...(data.cloud?.links || []).map(l => ext(l.url, l.name, "chip")));

  const statusText = c => c.status === "ended" ? "종료됨" : c.days_left === null ? "종료일 미정" : `D-${fmt.num(c.days_left)}`;
  $("eol-grid").replaceChildren(...(eol.length ? eol.map(p => h("div", { class: "eol-card" }, [
    h("div", { class: "eol-head" }, [h("strong", { text: p.name }), ext(p.url, "상세", "meta")]),
    h("ul", null, p.cycles.length ? p.cycles.map(c => h("li", { class: `eol-row st-${c.status}` }, [
      h("span", { class: "eol-ver", text: c.cycle + (c.lts ? " LTS" : "") }),
      h("span", { class: "eol-date", text: c.eol || "–" }),
      h("span", { class: "eol-left", text: statusText(c) })])) : [h("li", { class: "meta", text: "지원 중인 버전 정보 없음" })]),
  ])) : [h("p", { class: "empty", text: "EOL 데이터 없음" })]));
})();
