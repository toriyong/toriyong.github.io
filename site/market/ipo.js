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
    $("ipo-rows").replaceChildren(h("tr", null, h("td", { colspan: 10, class: "empty", text: "데이터 없음" })));
    return;
  }
  const today = todayKst();

  // ---------- 표시 범위: 오늘 기준 30일
  // 청약 시작이 30일 넘게 남은 종목은 일정 변경·철회 가능성이 커서 기본 목록에서 접어 둔다.
  const WINDOW_DAYS = 30;
  const LISTED_KEEP_DAYS = 14;               // 상장 완료는 최근 2주만
  const shiftIso = (n) => {
    const d = new Date(today + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const horizon = shiftIso(WINDOW_DAYS);
  const listedFrom = shiftIso(-LISTED_KEEP_DAYS);
  const keyDate = i => i.sub_start || i.listing_date || i.rcept_dt || "9999-12-31";
  const isLater = i => i.status === "upcoming" && !!i.sub_start && i.sub_start > horizon;
  const isOldListed = i => i.status === "listed" && (i.listing_date || i.sub_end || "") < listedFrom;
  const all = (data.items || []).filter(i => i.grade !== "spac" && !i.is_spac)   // 스팩 제외
    .slice().sort((a, b) => keyDate(a).localeCompare(keyDate(b)));
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

  // ---------- 요약
  const count = pred => items.filter(pred).length;
  const nonSpac = i => i.grade !== "spac";
  $("summary").replaceChildren(
    ...[["subscribing", "청약 중"], ["upcoming", "청약 예정"], ["awaiting_listing", "상장 대기"]]
      .map(([s, label]) => h("span", { class: "chip" }, [label, h("strong", { text: count(i => i.status === s && nonSpac(i)) })])),
    ...GRADE_ORDER.map(g => h("span", { class: "chip" }, [badge(g), h("strong", { text: count(i => i.grade === g) })])),
  );
  $("window-note").textContent =
    `오늘부터 ${WINDOW_DAYS}일 안(~${fmt.md(horizon)})에 청약하는 종목과 청약 중·상장 대기 종목, 최근 ${LISTED_KEEP_DAYS}일 상장 종목 기준 · 스팩 제외`;

  // ---------- 캘린더 (평일만 표시)
  const iso = d => d.toISOString().slice(0, 10);
  const utc = (y, m, d) => new Date(Date.UTC(y, m, d));
  const addDays = (d, n) => utc(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + n);

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
        h("a", { class: `ev ${kind}`, href: "#row-" + item.corp_code, title: `${item.corp_name} · ${GRADE[item.grade] || ""}` }, [
          h("span", { class: "ev-kind", text: kind === "sub" ? "청약" : "상장" }), item.corp_name,
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
          h("a", { class: `ev ${kind}`, href: "#row-" + item.corp_code }, [
            h("span", { class: "ev-kind", text: kind === "sub" ? "청약" : "상장" }), item.corp_name,
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
    if (!rows.length) out.push(h("tr", null, h("td", { colspan: 10, class: "empty", text: "30일 안에 해당하는 종목이 없습니다" })));
    if (extra.length) {
      out.push(h("tr", { class: "later-toggle" }, h("td", { colspan: 10 },
        h("button", { type: "button", class: "more", "aria-expanded": String(showLater),
          text: showLater ? `${WINDOW_DAYS}일 이후 예정 ${extra.length}건 접기`
                          : `${WINDOW_DAYS}일 이후 예정 ${extra.length}건 보기 (일정 변경·철회 가능)`,
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
})();
