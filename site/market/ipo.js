// 증시 탭: 공모주 요약 · 캘린더 · 목록 · 등급 기준
(async function () {
  "use strict";
  const { h, fmt, todayKst, loadJson } = window.Hub;

  const GRADE = {
    scalp: "단타 ⭐⭐", swing: "스윙 ⭐", watch: "관찰",
    pending: "판정 보류", exclude: "제외 ❌", spac: "스팩",
  };
  const GRADE_ORDER = ["scalp", "swing", "watch", "pending", "exclude"];
  const STATUS = {
    subscribing: "청약 중", upcoming: "청약 예정", awaiting_listing: "상장 대기",
    listed: "상장 완료", unknown: "일정 미정",
  };
  const FILTERS = [
    ["all", "전체"], ["subscribing", "청약 중"], ["upcoming", "청약 예정"],
    ["awaiting_listing", "상장 대기"], ["listed", "상장 완료"],
  ];

  const $ = id => document.getElementById(id);
  const badge = g => h("span", { class: `badge g-${g}`, text: GRADE[g] || g });

  let data;
  try {
    data = await loadJson("data/ipo.json");
  } catch (e) {
    $("summary").replaceChildren(h("span", { class: "meta", text: "아직 수집된 데이터가 없습니다. 첫 배포 후 자동 수집이 끝나면 표시됩니다." }));
    $("ipo-rows").replaceChildren(h("tr", null, h("td", { colspan: 11, class: "empty", text: "데이터 없음" })));
    return;
  }
  const today = todayKst();

  // ---------- 표시 범위: 오늘 기준 영업일 15일(약 3주)
  // 청약 시작이 그보다 늦은 종목은 일정 변경·철회 가능성이 커서 기본 목록에서 접어 둔다.
  const WINDOW_DAYS = 15;                    // 영업일(평일) 기준 ≈ 3주
  const LISTED_KEEP_DAYS = 14;               // 상장 완료는 최근 2주만
  const shiftIso = (n) => {
    const d = new Date(today + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  // 오늘부터 평일만 세어 WINDOW_DAYS 번째 날까지 (공휴일은 반영하지 않음)
  const addBizDays = (n) => {
    const d = new Date(today + "T00:00:00Z");
    let left = n;
    while (left > 0) {
      d.setUTCDate(d.getUTCDate() + 1);
      const w = d.getUTCDay();
      if (w !== 0 && w !== 6) left--;
    }
    return d.toISOString().slice(0, 10);
  };
  const horizon = addBizDays(WINDOW_DAYS);
  const listedFrom = shiftIso(-LISTED_KEEP_DAYS);
  const keyDate = i => i.sub_start || i.listing_date || i.rcept_dt || "9999-12-31";
  const isLater = i => i.status === "upcoming" && !!i.sub_start && i.sub_start > horizon;
  const isOldListed = i => i.status === "listed" && (i.listing_date || i.sub_end || "") < listedFrom;
  // 상태는 수집 시각이 아니라 '보는 시각'의 오늘 날짜로 다시 계산한다
  // (process/market/grade_ipo.py status_of 와 같은 규칙 → 자정이 지나 새로고침하면 바로 반영)
  const statusOf = i => {
    const s = i.sub_start, e = i.sub_end || i.sub_start, lst = i.listing_date;
    if (lst && lst < today) return "listed";
    if (s && today < s) return "upcoming";
    if (s && e && s <= today && today <= e) return "subscribing";
    if (e && e < today) return "awaiting_listing";
    return i.status || "unknown";
  };
  const all = (data.items || []).filter(i => i.grade !== "spac" && !i.is_spac)   // 스팩 제외
    .map(i => ({ ...i, status: statusOf(i) })).sort((a, b) => keyDate(a).localeCompare(keyDate(b)));
  const items = all.filter(i => !isLater(i) && !isOldListed(i));   // 요약·목록 기본 대상
  const later = all.filter(isLater);
  let showLater = false;

  // ---------- 배너 · 기준 시각
  if (data.sample) $("banner-sample").classList.remove("hidden");
  if (data.stale) {
    const b = $("banner-stale");
    b.textContent = `최신 수집에 실패해 직전 데이터를 표시하고 있습니다. (${data.stale_reason || "원인 미상"})`;
    b.classList.remove("hidden");
  }
  $("updated").textContent = `기준 시각 ${fmt.stamp(data.updated_at)} (KST)`;

  // ---------- 요약 (칩을 누르면 아래에 해당 종목 간단 정보)
  const count = pred => items.filter(pred).length;
  const SUMMARY = [
    ...[["subscribing", "청약 중"], ["upcoming", "청약 예정"], ["awaiting_listing", "상장 대기"]]
      .map(([s, label]) => ({ id: "s-" + s, label, pred: i => i.status === s, head: () => label })),
    ...GRADE_ORDER.map(g => ({ id: "g-" + g, grade: g, pred: i => i.grade === g, head: () => GRADE[g] })),
  ];
  // ---------- 청약 카드 (요약의 '청약 중'·'청약 예정'을 펼치면 표시)
  function won(v) { return (v === null || v === undefined) ? "–" : `${fmt.num(v)}원`; }
  function dleft(d) { return Math.round((new Date(d + "T00:00:00Z") - new Date(today + "T00:00:00Z")) / 864e5); }
  function subCard(it) {
    const price = it.offer_price || (it.band ? it.band[1] : it.price);
    const minQ = it.min_shares;
    const rate = it.margin_rate ?? 50;
    const deposit = minQ && price ? Math.round(minQ * price * rate / 100) : null;
    const end = it.sub_end || it.sub_start;
    const when = it.status === "subscribing"
      ? (dleft(end) === 0 ? "오늘 마감" : `마감 D-${dleft(end)}`)
      : `D-${dleft(it.sub_start)}`;
    const row = (k, v, cls) => h("div", { class: "kv" + (cls ? " " + cls : "") }, [h("span", { class: "k", text: k }), h("span", { class: "v" }, v)]);
    return h("article", { class: "next-card" + (it.status === "subscribing" ? " live" : "") }, [
      h("div", { class: "next-head" }, [
        h("a", { href: "#row-" + it.corp_code }, h("strong", { class: "next-name", text: it.corp_name })),
        h("span", { class: "next-when" + (it.status === "subscribing" ? " live" : ""), text: when }),
      ]),
      h("div", { class: "next-badges" }, [
        h("span", { class: "tag", text: STATUS[it.status] }),
        it.subscribe ? h("span", { class: `badge sub-${it.subscribe.level}`, text: `청약 판단 ${it.subscribe.label}` }) : h("span", { class: "badge g-pending", text: "수요예측 전" }),
        badge(it.grade),
      ]),
      h("div", { class: "kvs" }, [
        row("청약일", fmt.period(it.sub_start, it.sub_end)),
        row("공모가", it.offer_price ? `${won(it.offer_price)} (확정)` : it.band ? `희망 ${fmt.num(it.band[0])}~${fmt.num(it.band[1])}원` : won(it.price)),
        row("최소수량(균등)", minQ ? `${fmt.num(minQ)}주` : "원문 확인"),
        row("최소 증거금", deposit ? `${won(deposit)}${it.offer_price ? "" : " (상단 기준)"}` : "–", "hl"),
        row("주관사", (it.underwriters || []).join(", ") || "–"),
        row("기관 경쟁률", fmt.ratio(it.demand_ratio)),
        row("확약률 · 유통", `${fmt.pct(it.lockup_ratio)} · ${fmt.pct(it.float_ratio)}`),
        row("최고 한도", it.max_shares ? `${fmt.num(it.max_shares)}주` : "–"),
        row("환불·납입일", it.pay_date ? fmt.md(it.pay_date) : "–"),
      ]),
      h("a", { class: "next-link", href: it.dart_url, target: "_blank", rel: "noopener noreferrer", text: "신고서 원문 ↗" }),
    ]);
  }

  // 증시 탭을 열면 '청약 중'(없으면 '청약 예정')을 바로 펼쳐 둔다
  let openChip = count(i => i.status === "subscribing") ? "s-subscribing"
    : count(i => i.status === "upcoming") ? "s-upcoming" : null;
  function renderSummary() {
    $("summary").replaceChildren(...SUMMARY.map(c => {
      const n = count(c.pred);
      return h("button", {
        type: "button", class: "chip chip-btn" + (openChip === c.id ? " on" : ""),
        "aria-expanded": String(openChip === c.id), "aria-controls": "summary-detail", disabled: n ? null : "",
        onclick: () => { openChip = openChip === c.id ? null : c.id; renderSummary(); },
      }, [c.grade ? badge(c.grade) : c.label, h("strong", { text: n })]);
    }));
    const box = $("summary-detail");
    const c = SUMMARY.find(x => x.id === openChip);
    if (!c) { box.classList.add("hidden"); box.replaceChildren(); return; }
    const list = items.filter(c.pred);
    box.classList.remove("hidden");
    if (c.id === "s-subscribing" || c.id === "s-upcoming") {
      const sorted = list.slice().sort((x, y) => (x.sub_start || "9").localeCompare(y.sub_start || "9"));
      box.replaceChildren(
        h("div", { class: "sd-head" }, h("strong", { text: `${c.head()} ${list.length}건 · 청약일 빠른 순` })),
        h("div", { class: "next-grid" }, sorted.map(subCard)),
        h("p", { class: "meta", text: "최소 증거금 = 최소 청약수량(균등 배정 최소) × 공모가 × 증거금률. 공모가 확정 전에는 희망밴드 상단 기준. 청약 조건은 증권사별로 다를 수 있으니 원문을 확인하세요." }),
      );
      return;
    }
    box.replaceChildren(
      h("div", { class: "sd-head" }, h("strong", { text: `${c.head()} ${list.length}건` })),
      h("ul", { class: "sd-list" }, list.map(it => h("li", null, [
        h("a", { class: "sd-name", href: "#row-" + it.corp_code, text: it.corp_name,
          onclick: () => { filter = "all"; showLater = false; renderFilters(); renderRows(); } }),
        h("span", { class: "sd-meta" }, [
          h("span", { text: `${STATUS[it.status] || "–"} · ${fmt.period(it.sub_start, it.sub_end) || "일정 미정"}` }),
          h("span", { text: `공모가 ${fmt.num(it.offer_price || it.price)}${it.offer_price ? "(확정)" : ""}` }),
          it.demand_ratio != null ? h("span", { text: `경쟁률 ${fmt.ratio(it.demand_ratio)}` }) : null,
          it.lockup_ratio != null ? h("span", { text: `확약 ${fmt.pct(it.lockup_ratio)}` }) : null,
        ]),
        h("span", { class: "sd-badges" }, [
          c.grade ? null : badge(it.grade),
          it.subscribe ? h("span", { class: `badge sub-${it.subscribe.level}`, text: it.subscribe.label }) : null,
        ]),
      ]))),
    );
  }
  renderSummary();

  $("window-note").textContent =
    `오늘부터 영업일 ${WINDOW_DAYS}일 안(~${fmt.md(horizon)})에 청약하는 종목과 청약 중·상장 대기 종목, 최근 ${LISTED_KEEP_DAYS}일 상장 종목 기준 · 스팩 제외`;

  // ---------- 캘린더 (평일만 표시)
  const iso = d => d.toISOString().slice(0, 10);
  const utc = (y, m, d) => new Date(Date.UTC(y, m, d));
  const addDays = (d, n) => utc(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + n);

  const EV_LABEL = { sub: "청약", list: "상장" };
  const evHref = (kind, item) => item.status === "listed" ? "results/#r-" + item.corp_code : "#row-" + item.corp_code;
  const evText = (kind, item) => item.corp_name;
  const events = {};   // 'YYYY-MM-DD' → [{kind, item}]
  const push = (day, kind, item) => (events[day] = events[day] || []).push({ kind, item });
  for (const it of all) {
    if (it.sub_start) {
      const end = it.sub_end || it.sub_start;
      for (let d = new Date(it.sub_start + "T00:00:00Z"); iso(d) <= end; d = addDays(d, 1)) push(iso(d), "sub", it);
    }
    if (it.listing_date) push(it.listing_date, "list", it);
  }

  const params = new URLSearchParams(location.search);
  let [cy, cm] = (params.get("month") || today.slice(0, 7)).split("-").map(Number);
  if (!cy || !cm) [cy, cm] = today.slice(0, 7).split("-").map(Number);

  function renderCalendar() {
    $("cal-title").textContent = `${cy}년 ${cm}월`;
    const first = utc(cy, cm - 1, 1);
    const last = utc(cy, cm, 0);
    const start = addDays(first, -((first.getUTCDay() + 6) % 7));        // 그 주 월요일
    const end = addDays(last, (5 - last.getUTCDay() + 7) % 7);            // 그 주 금요일
    const cells = ["월", "화", "수", "목", "금"].map(d => h("div", { class: "cal-dow", text: d }));
    for (let d = start; d <= end; d = addDays(d, 1)) {
      const dow = d.getUTCDay();
      if (dow === 0 || dow === 6) continue;
      const key = iso(d);
      const evs = (events[key] || []).map(({ kind, item }) =>
        h("a", { class: `ev ${kind}`, href: evHref(kind, item), title: `${evText(kind, item)} · ${GRADE[item.grade] || ""}` }, [
          h("span", { class: "ev-kind", text: EV_LABEL[kind] }), evText(kind, item),
        ]));
      cells.push(h("div", {
        class: ["cal-day", d.getUTCMonth() !== cm - 1 ? "out" : "", key === today ? "today" : ""].join(" ").trim(),
      }, [h("div", { class: "cal-date", text: d.getUTCDate() }), ...evs]));
    }
    $("calendar").replaceChildren(...cells);

    // 모바일용 날짜별 목록(아젠다): 이번 달에 일정이 있는 날만
    const DOW = ["일", "월", "화", "수", "목", "금", "토"];
    const prefix = `${cy}-${String(cm).padStart(2, "0")}`;
    const days = Object.keys(events).filter(k => k.startsWith(prefix)).sort();
    $("agenda").replaceChildren(...(days.length ? days.map(k => {
      const d = new Date(k + "T00:00:00Z");
      return h("li", { class: "agenda-day" + (k === today ? " today" : "") }, [
        h("div", { class: "agenda-date" }, [h("strong", { text: d.getUTCDate() }), h("span", { text: DOW[d.getUTCDay()] })]),
        h("div", { class: "agenda-evs" }, events[k].map(({ kind, item }) =>
          h("a", { class: `ev ${kind}`, href: evHref(kind, item) }, [
            h("span", { class: "ev-kind", text: EV_LABEL[kind] }), evText(kind, item),
            item.grade && item.grade !== "spac" ? h("span", { class: `badge g-${item.grade} ev-badge`, text: GRADE[item.grade] }) : null,
          ]))),
      ]);
    }) : [h("li", { class: "empty", text: "이번 달 일정이 없습니다" })]));
    const url = new URL(location.href);
    url.searchParams.set("month", `${cy}-${String(cm).padStart(2, "0")}`);
    history.replaceState(null, "", url);
  }
  const shift = n => { const d = utc(cy, cm - 1 + n, 1); cy = d.getUTCFullYear(); cm = d.getUTCMonth() + 1; renderCalendar(); };
  $("cal-prev").addEventListener("click", () => shift(-1));
  $("cal-next").addEventListener("click", () => shift(1));
  $("cal-today").addEventListener("click", () => { [cy, cm] = today.slice(0, 7).split("-").map(Number); renderCalendar(); });
  renderCalendar();

  // ---------- 목록
  let filter = "all";
  function renderFilters() {
    $("filters").replaceChildren(...FILTERS.map(([id, label]) =>
      h("button", { type: "button", class: filter === id ? "on" : null, text: label,
        onclick: () => { filter = id; renderFilters(); renderRows(); } })));
  }
  function subCell(sv) {
    if (!sv) return h("span", { class: "meta", text: "수요예측 전" });
    const tip = [sv.basis, ...(sv.notes || []).map(n => "↓ " + n), sv.to_next].filter(Boolean);
    return h("details", { class: "reasons" }, [
      h("summary", null, h("span", { class: `badge sub-${sv.level}`, text: sv.label })),
      h("ul", null, tip.map(t => h("li", { text: t }))),
    ]);
  }
  function row(it, dim) {
    return h("tr", { id: "row-" + it.corp_code, class: dim ? "dim" : null }, [
      h("td", { class: "name card-title" }, [h("strong", { text: it.corp_name }),
        h("span", { class: "sub-line", text: [it.market, it.sector].filter(Boolean).join(" · ") || "시장·섹터 미입력" })]),
      h("td", { "data-label": "등급" }, h("details", { class: "reasons" }, [
        h("summary", null, badge(it.grade)),
        h("ul", null, (it.reasons || []).map(r => h("li", { text: r }))),
      ])),
      h("td", { "data-label": "상태", text: STATUS[it.status] || "–" }),
      h("td", { "data-label": "청약일" }, [fmt.period(it.sub_start, it.sub_end),
        it.listing_date ? h("span", { class: "sub-line", text: `상장 ${fmt.md(it.listing_date)}` }) : null]),
      h("td", { class: "num", "data-label": "공모가(원)" }, [fmt.num(it.offer_price || it.price),
        h("span", { class: "sub-line", text: it.offer_price ? "확정" : (it.band ? `희망 ${fmt.num(it.band[0])}~${fmt.num(it.band[1])}` : "신고서 기재가") })]),
      h("td", { "data-label": "주관사", class: "uw", text: (it.underwriters || []).join(", ") || "–" }),
      h("td", { class: "num", "data-label": "경쟁률", text: fmt.ratio(it.demand_ratio) }),
      h("td", { "data-label": "청약 판단" }, subCell(it.subscribe)),
      h("td", { class: "num", "data-label": "확약률", text: fmt.pct(it.lockup_ratio) }),
      h("td", { class: "num", "data-label": "유통물량", text: fmt.pct(it.float_ratio) }),
      h("td", { "data-label": "공시" }, h("a", { href: it.dart_url, target: "_blank", rel: "noopener noreferrer", text: "원문" })),
    ]);
  }
  function renderRows() {
    const pick = i => filter === "all" || i.status === filter;
    const rows = items.filter(pick);
    const extra = later.filter(pick);
    const out = rows.map(it => row(it, false));
    if (!rows.length) out.push(h("tr", null, h("td", { colspan: 11, class: "empty", text: "기간 안에 해당하는 종목이 없습니다" })));
    if (extra.length) {
      out.push(h("tr", { class: "later-toggle" }, h("td", { colspan: 11 },
        h("button", { type: "button", class: "more", "aria-expanded": String(showLater),
          text: showLater ? `${fmt.md(horizon)} 이후 예정 ${extra.length}건 접기`
                          : `${fmt.md(horizon)} 이후 예정 ${extra.length}건 보기 (일정 변경·철회 가능)`,
          onclick: () => { showLater = !showLater; renderRows(); } }))));
      if (showLater) out.push(...extra.map(it => row(it, true)));
    }
    $("ipo-rows").replaceChildren(...out);
  }
  renderFilters();
  renderRows();

  // ---------- 등급 기준
  const legend = data.legend || {};
  $("legend").replaceChildren(...["scalp", "swing", "watch", "exclude", "pending"]
    .filter(g => legend[g])
    .map(g => h("li", null, [badge(g), h("span", { text: legend[g].replace(/^[^—]*—\s*/, "") })])));

  // ---------- 청약 판단 기준
  const sr = data.subscribe_rule || {};
  $("sub-legend").replaceChildren(...(sr.tiers || []).map(t =>
    h("li", null, [h("span", { class: `badge sub-${t.level}`, text: t.label }), h("span", { text: t.desc })])));
  const adj = [];
  if (sr.low_lockup != null) adj.push(`확약률 ${sr.low_lockup}% 미만`);
  if (sr.below_band_penalty) adj.push("희망밴드 하단 미만 확정");
  $("sub-rule-note").textContent = (adj.length ? `${adj.join(", ")}이면 한 단계씩 낮춥니다. ` : "") +
    "참고용 고정 기준이며 수익을 보장하지 않습니다. 기준값은 config/grading.yml 에서 바꿀 수 있습니다.";
})();
