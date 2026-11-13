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
  const items = data.items || [];
  const today = todayKst();

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

  // ---------- 캘린더 (평일만 표시)
  const iso = d => d.toISOString().slice(0, 10);
  const utc = (y, m, d) => new Date(Date.UTC(y, m, d));
  const addDays = (d, n) => utc(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + n);

  const events = {};   // 'YYYY-MM-DD' → [{kind, item}]
  const push = (day, kind, item) => (events[day] = events[day] || []).push({ kind, item });
  for (const it of items) {
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
  function renderRows() {
    const rows = items.filter(i => filter === "all" || i.status === filter);
    if (!rows.length) {
      $("ipo-rows").replaceChildren(h("tr", null, h("td", { colspan: 10, class: "empty", text: "해당하는 종목이 없습니다" })));
      return;
    }
    $("ipo-rows").replaceChildren(...rows.map(it => h("tr", { id: "row-" + it.corp_code }, [
      h("td", { class: "name" }, [h("strong", { text: it.corp_name }),
        h("span", { class: "sub-line", text: [it.market, it.sector].filter(Boolean).join(" · ") || "시장·섹터 미입력" })]),
      h("td", { text: STATUS[it.status] || "–" }),
      h("td", null, [fmt.period(it.sub_start, it.sub_end),
        it.listing_date ? h("span", { class: "sub-line", text: `상장 ${fmt.md(it.listing_date)}` }) : null]),
      h("td", { class: "num" }, [fmt.num(it.offer_price || it.price),
        h("span", { class: "sub-line", text: it.offer_price ? "확정" : (it.band ? `희망 ${fmt.num(it.band[0])}~${fmt.num(it.band[1])}` : "신고서 기재가") })]),
      h("td", { text: (it.underwriters || []).join(", ") || "–" }),
      h("td", { class: "num", text: fmt.ratio(it.demand_ratio) }),
      h("td", { class: "num", text: fmt.pct(it.lockup_ratio) }),
      h("td", { class: "num", text: fmt.pct(it.float_ratio) }),
      h("td", null, h("details", { class: "reasons" }, [
        h("summary", null, badge(it.grade)),
        h("ul", null, (it.reasons || []).map(r => h("li", { text: r }))),
      ])),
      h("td", null, h("a", { href: it.dart_url, target: "_blank", rel: "noopener noreferrer", text: "원문" })),
    ])));
  }
  renderFilters();
  renderRows();

  // ---------- 등급 기준
  const legend = data.legend || {};
  $("legend").replaceChildren(...["scalp", "swing", "watch", "exclude", "pending"]
    .filter(g => legend[g])
    .map(g => h("li", null, [badge(g), h("span", { text: legend[g].replace(/^[^—]*—\s*/, "") })])));
})();
