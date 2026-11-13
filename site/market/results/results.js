// 증시 > 성적표: 청약 판단별 성과 · 최근 상장 수익률 · 섹터 주목도
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);

  let data;
  try {
    data = await loadJson("../data/results.json");
  } catch (e) {
    $("result-rows").replaceChildren(h("tr", null, h("td", { colspan: 11, class: "empty", text: "아직 성적표 데이터가 없습니다. 다음 자동 수집 후 표시됩니다." })));
    return;
  }
  $("updated").textContent = `기준 시각 ${fmt.stamp(data.updated_at)} (KST)`;
  if (!data.has_prices) $("banner-noprice").classList.remove("hidden");

  // 수익률 표시: +12.3% / −4.5%, 색으로 구분
  const R = v => (v === null || v === undefined)
    ? h("span", { class: "meta", text: "–" })
    : h("span", { class: v > 0 ? "up" : v < 0 ? "down" : null, text: `${v > 0 ? "+" : ""}${fmt.num(v, 1)}%` });
  const subBadge = sv => sv ? h("span", { class: `badge sub-${sv.level}`, text: sv.label }) : h("span", { class: "meta", text: "–" });

  // ---------- 청약 판단별 성과
  const bk = data.buckets || [];
  $("bucket-rows").replaceChildren(...(bk.length ? bk.map(b => h("tr", null, [
    h("td", { class: "card-title" }, h("span", { class: `badge sub-${b.level}`, text: b.label })),
    h("td", { class: "num", "data-label": "종목 수", text: data.has_prices ? `${b.with_price} / ${b.count}` : String(b.count) }),
    h("td", { class: "num", "data-label": "시가" }, R(b.avg_open)),
    h("td", { class: "num", "data-label": "D0 종가" }, R(b.avg_d0)),
    h("td", { class: "num", "data-label": "D+5" }, R(b.avg_d5)),
    h("td", { class: "num", "data-label": "D+30" }, R(b.avg_d30)),
    h("td", { class: "num", "data-label": "D0 상승 비율", text: b.win_d0 === null || b.win_d0 === undefined ? "–" : `${fmt.num(b.win_d0, 0)}%` }),
  ])) : [h("tr", null, h("td", { colspan: 7, class: "empty", text: "데이터 없음" }))]));

  // ---------- 최근 상장 성적 (기간 필터)
  const PERIODS = [["30", "1개월"], ["90", "3개월"], ["180", "6개월"], ["all", "전체"]];
  let period = "90";
  const since = days => {
    const d = new Date(Date.now() + 9 * 3600e3);
    d.setUTCDate(d.getUTCDate() - Number(days));
    return d.toISOString().slice(0, 10);
  };
  function renderPeriod() {
    $("period").replaceChildren(...PERIODS.map(([k, label]) => h("button", {
      type: "button", class: "filter" + (k === period ? " on" : ""), "aria-pressed": String(k === period), text: label,
      onclick: () => { period = k; renderPeriod(); renderRows(); },
    })));
  }
  function renderRows() {
    const from = period === "all" ? "" : since(period);
    const rows = (data.items || []).filter(i => (i.listing_date || "") >= from);
    $("result-rows").replaceChildren(...(rows.length ? rows.map(it => {
      const r = it.returns || {};
      return h("tr", { id: "r-" + it.corp_code }, [
        h("td", { class: "name card-title" }, [h("strong", { text: it.corp_name }),
          h("span", { class: "sub-line", text: [it.market, it.sector].filter(Boolean).join(" · ") || "–" })]),
        h("td", { "data-label": "상장일", text: fmt.md(it.listing_date) }),
        h("td", { class: "num", "data-label": "공모가", text: fmt.num(it.offer_price || it.price) }),
        h("td", { class: "num", "data-label": "경쟁률", text: fmt.ratio(it.demand_ratio) }),
        h("td", { "data-label": "청약 판단" }, subBadge(it.subscribe)),
        h("td", { class: "num", "data-label": "시가" }, R(r.open)),
        h("td", { class: "num", "data-label": "D0 종가" }, R(r.d0)),
        h("td", { class: "num", "data-label": "D+1" }, R(r.d1)),
        h("td", { class: "num", "data-label": "D+5" }, R(r.d5)),
        h("td", { class: "num", "data-label": "D+30" }, R(r.d30)),
        h("td", { class: "num", "data-label": "현재" }, R(r.last)),
      ]);
    }) : [h("tr", null, h("td", { colspan: 11, class: "empty", text: "기간 안에 상장한 종목이 없습니다" }))]));
    if (location.hash) document.querySelector(location.hash)?.classList.add("hl");
  }
  renderPeriod();
  renderRows();

  // ---------- 섹터 주목도
  const secs = data.sectors_90d || [];
  const maxN = Math.max(1, ...secs.map(s => s.count));
  $("sectors").replaceChildren(...(secs.length ? secs.slice(0, 12).map(s => h("div", { class: "sector" }, [
    h("div", { class: "sector-head" }, [h("strong", { text: s.sector }), h("span", { class: "sector-n", text: `${s.count}건` })]),
    h("div", { class: "bar", "aria-hidden": "true" }, h("span", { style: null, class: "bar-fill", "data-w": Math.round(s.count / maxN * 100) })),
    h("div", { class: "sector-meta" }, [
      h("span", { text: `평균 경쟁률 ${fmt.ratio(s.avg_demand)}` }),
      s.avg_d0 !== null && s.avg_d0 !== undefined ? h("span", null, ["D0 ", R(s.avg_d0)]) : null,
      s.avg_d5 !== null && s.avg_d5 !== undefined ? h("span", null, ["D+5 ", R(s.avg_d5)]) : null,
    ]),
    h("div", { class: "sector-names", text: s.names.slice(0, 5).join(", ") + (s.names.length > 5 ? ` 외 ${s.names.length - 5}` : "") }),
  ])) : [h("p", { class: "meta", text: "최근 90일 상장 종목이 없습니다" })]));
  // CSP(style-src 'self')로 인라인 style 속성을 쓰지 않으므로 막대 길이는 CSSOM으로 지정
  document.querySelectorAll(".bar-fill").forEach(el => { el.style.width = el.dataset.w + "%"; });
})();
