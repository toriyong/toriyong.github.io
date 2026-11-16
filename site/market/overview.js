// 증시 종합 — 공모주·관심종목·성적표의 요점만 모아 보여 준다. 자세한 내용은 각 탭에서.
(function () {
  "use strict";
  const { h, fmt, todayKst, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);
  const D = s => new Date(s + "T00:00:00+09:00");
  const dleft = (s, today) => Math.round((D(s) - D(today)) / 864e5);
  const fail = (el, msg) => { el.textContent = msg; };
  const pct = v => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  const cls = v => (v > 0 ? "up" : v < 0 ? "down" : "");

  // ---------------------------------------------------------------- 공모주 일정
  (async function ipo() {
    const box = $("ov-ipo");
    let d;
    try { d = await loadJson("data/ipo.json"); } catch (e) { return fail(box, "공모주 데이터를 불러오지 못했습니다."); }
    const today = todayKst();
    const key = x => x.sub_start || x.listing_date || "9999-12-31";
    const soon = (d.items || [])
      .filter(x => (x.listing_date || x.sub_end || x.sub_start || "") >= today)
      .sort((a, b) => key(a).localeCompare(key(b)))
      .slice(0, 5);
    if (!soon.length) return fail(box, "예정된 공모주 일정이 없습니다.");
    box.classList.remove("meta");
    box.replaceChildren(h("ul", { class: "plain ov-list" }, soon.map(x => {
      const s = x.sub_start, e = x.sub_end, l = x.listing_date;
      let state = "", when = "";
      if (s && e && s <= today && today <= e) { state = "청약 중"; when = `~ ${fmt.md(e)}`; }
      else if (s && s > today) { state = "청약 예정"; when = `${fmt.md(s)} · D-${dleft(s, today)}`; }
      else if (l && l >= today) { state = "상장 예정"; when = `${fmt.md(l)} · D-${dleft(l, today)}`; }
      const lv = x.subscribe && x.subscribe.level;
      return h("li", null, [
        h("strong", { text: x.corp_name || "-" }),
        lv ? h("span", { class: `pill lv-${lv}`, text: x.subscribe.label }) : null,
        h("span", { class: "meta", text: ` ${state} · ${when}${x.market ? " · " + x.market : ""}` }),
      ]);
    })));
  })();

  // ---------------------------------------------------------------- 관심종목
  (async function watch() {
    const box = $("ov-watch");
    let d;
    try { d = await loadJson("data/watchlist.json"); } catch (e) { return fail(box, "관심종목 데이터를 불러오지 못했습니다."); }
    const stocks = d.stocks || [];
    if (!stocks.length) return fail(box, "등록된 관심종목이 없습니다. 관심종목 탭에서 추가하세요.");
    box.classList.remove("meta");
    box.replaceChildren(h("ul", { class: "plain ov-list" }, stocks.slice(0, 6).map(x => {
      const p = x.price || {};
      const r = typeof p.change_pct === "number" ? p.change_pct : null;
      const news = (x.news || []).length + (x.disclosures || []).length;
      return h("li", null, [
        h("strong", { text: x.name || "-" }),
        typeof p.price === "number" ? h("span", { class: "meta", text: ` ${fmt.num(p.price)}원` }) : null,
        r !== null ? h("span", { class: `delta ${cls(r)}`, text: ` ${pct(r)}` }) : null,
        typeof x.upside === "number"
          ? h("span", { class: "meta", text: ` · 목표가 대비 ${pct(x.upside)}` }) : null,
        news ? h("span", { class: "meta", text: ` · 소식 ${news}건` }) : null,
      ]);
    })));
  })();

  // ---------------------------------------------------------------- 성적표
  (async function results() {
    const box = $("ov-results");
    let d;
    try { d = await loadJson("data/results.json"); } catch (e) { return fail(box, "성적표 데이터를 불러오지 못했습니다."); }
    const buckets = (d.buckets || []).filter(b => b.count);
    if (!buckets.length) return fail(box, "집계된 성적표가 없습니다.");
    box.classList.remove("meta");
    box.replaceChildren(
      h("p", { class: "meta", text: "대응 구간 등급별 상장일 평균 수익률입니다. 지난 결과이며 앞으로를 보장하지 않습니다." }),
      h("div", { class: "nt-scroll" }, h("table", { class: "nt-table" }, [
        h("thead", null, h("tr", null, ["등급", "건수", "상장일 평균", "상장일 플러스"].map(t => h("th", { text: t })))),
        h("tbody", null, buckets.map(b => h("tr", null, [
          h("td", { text: b.label }),
          h("td", { text: `${b.count}건` }),
          h("td", { class: typeof b.avg_d0 === "number" ? cls(b.avg_d0) : "",
            text: typeof b.avg_d0 === "number" ? pct(b.avg_d0) : "-" }),
          h("td", { text: typeof b.win_d0 === "number" ? `${b.win_d0.toFixed(0)}%` : "-" }),
        ]))),
      ])),
    );
  })();
})();
