// 증시 > 관심종목: 목표가 도달률 · 최근 뉴스 · DART 공시
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);

  let data;
  try {
    data = await loadJson("../data/watchlist.json");
  } catch (e) {
    $("target-rows").replaceChildren(h("tr", null, h("td", { colspan: 6, class: "empty", text: "아직 관심종목 데이터가 없습니다. 다음 자동 수집 후 표시됩니다." })));
    return;
  }
  $("updated").textContent = `기준 시각 ${fmt.stamp(data.updated_at)} (KST)`;
  const stocks = data.stocks || [];
  if (!stocks.length) $("banner-empty").classList.remove("hidden");
  if (!data.has_prices) $("banner-noprice").classList.remove("hidden");

  const pctSpan = (v, signed) => (v === null || v === undefined)
    ? h("span", { class: "meta", text: "–" })
    : h("span", { class: signed ? (v > 0 ? "up" : v < 0 ? "down" : null) : null, text: `${signed && v > 0 ? "+" : ""}${fmt.num(v, 1)}%` });
  const ext = (href, text) => h("a", { href, target: "_blank", rel: "noopener noreferrer", text });

  // ---------- 목표가 도달률 표
  $("target-rows").replaceChildren(...(stocks.length ? stocks.map(s => {
    const p = s.price || {};
    return h("tr", null, [
      h("td", { class: "name card-title" }, [h("a", { href: `https://finance.naver.com/item/main.naver?code=${s.stock_code}`, target: "_blank", rel: "noopener noreferrer", title: `${s.name} 시세 보기` }, h("strong", { text: s.name })),
        h("span", { class: "sub-line", text: s.stock_code })]),
      h("td", { class: "num", "data-label": "현재가" }, [fmt.num(p.price),
        p.change_pct !== undefined && p.change_pct !== null ? h("span", { class: "sub-line" }, pctSpan(p.change_pct, true)) : null]),
      h("td", { class: "num", "data-label": "평균 목표가", text: fmt.num(s.avg_target) }),
      h("td", { class: "num", "data-label": "도달률" }, s.attain === null || s.attain === undefined
        ? h("span", { class: "meta", text: s.avg_target ? "현재가 필요" : "목표가 미입력" })
        : h("span", { class: "attain" }, [h("span", { class: "attain-track" }, h("span", { class: "attain-bar", "data-w": Math.min(100, s.attain) })), `${fmt.num(s.attain, 1)}%`])),
      h("td", { class: "num", "data-label": "상승 여력" }, pctSpan(s.upside, true)),
      h("td", { "data-label": "목표가" }, (s.targets || []).length
        ? h("ul", { class: "plain" }, s.targets.slice(0, 4).map(t => h("li", { text: `${t.broker || "–"} ${fmt.num(t.price)}원 · ${fmt.md(t.date)}` })))
        : h("a", { class: "meta", href: `https://github.com/toriyong/toriyong.github.io/issues/new?template=watchlist.yml&action=${encodeURIComponent("목표가 추가")}&name=${encodeURIComponent(s.name)}&code=${s.stock_code}`, target: "_blank", rel: "noopener noreferrer", text: "목표가 입력 ↗" })),
    ]);
  }) : [h("tr", null, h("td", { colspan: 6, class: "empty", text: "관심종목 없음" }))]));
  // 인라인 style 속성 대신 CSSOM으로 막대 길이 지정 (CSP)
  document.querySelectorAll(".attain-bar").forEach(el => { el.style.width = el.dataset.w + "%"; });

  // ---------- 관심종목 뉴스 · 주요 공시 (종목별로 늘어놓지 않고 한데 모아 간략히)
  const PER_STOCK = 2;     // 종목당 최대 몇 건
  const TOTAL = 6;         // 전체 최대 몇 건

  // 일상적인 보고(지분 변동 신고 등)는 뒤로, 주가에 영향이 큰 공시는 앞으로
  const MINOR = ["임원ㆍ주요주주특정증권등소유상황보고서", "임원·주요주주특정증권등소유상황보고서",
    "최대주주등소유주식변동신고서", "주식등의대량보유상황보고서", "기업설명회", "IR개최",
    "풍문또는보도", "자기주식취득신탁계약체결결과", "일괄신고추가서류", "증권발행실적보고서"];
  const MAJOR = ["유상증자", "무상증자", "전환사채", "신주인수권부사채", "교환사채",
    "자기주식", "합병", "분할", "영업양수", "영업양도", "주식교환", "주식이전",
    "손익구조", "영업(잠정)실적", "매출액또는손익구조", "현금ㆍ현물배당", "현금·현물배당",
    "소송", "감사보고서", "사업보고서", "분기보고서", "반기보고서", "주요사항보고서",
    "최대주주변경", "유상감자", "상장폐지", "관리종목", "불성실공시", "투자주의", "거래정지"];
  const hit = (t, list) => list.some(k => (t || "").replace(/\s/g, "").includes(k.replace(/\s/g, "")));
  const rank = t => (hit(t, MAJOR) ? 2 : hit(t, MINOR) ? 0 : 1);

  // 종목별 상위 몇 건만 뽑아 한 줄로 합친다
  function merge(key, pick) {
    const rows = [];
    for (const s of stocks) rows.push(...(s[key] || []).slice().sort(pick).slice(0, PER_STOCK).map(x => ({ ...x, s })));
    return rows.sort(pick).slice(0, TOTAL);
  }
  const byDate = (a, b) => String(b.date || "").localeCompare(String(a.date || ""));
  const byRank = (a, b) => rank(b.title) - rank(a.title) || byDate(a, b);

  const tag = s => h("a", { class: "wl-tag", href: `https://finance.naver.com/item/main.naver?code=${s.stock_code}`,
    target: "_blank", rel: "noopener noreferrer", title: `${s.name} 시세 보기`, text: s.name });

  function feed(rows, empty, meta) {
    return rows.length ? h("ul", { class: "feed compact" }, rows.map(x => h("li", { class: "feed-item" }, [
      h("div", { class: "feed-meta" }, [tag(x.s), h("span", { class: "meta", text: meta(x) })]),
      h("a", { class: "feed-title", href: x.url, target: "_blank", rel: "noopener noreferrer", text: x.title }),
    ]))) : h("p", { class: "meta", text: empty });
  }

  $("stocks").replaceChildren(
    h("section", { class: "panel" }, [
      h("div", { class: "panel-head" }, [h("h2", { text: "관심종목 뉴스" }), h("span", { class: "meta", text: "최근 7일 · 종목당 최대 2건" })]),
      feed(merge("news", byDate), "최근 7일 뉴스 없음", x => `${x.source || ""} ${fmt.md(x.date)}`.trim()),
    ]),
    h("section", { class: "panel" }, [
      h("div", { class: "panel-head" }, [h("h2", { text: "주요 공시" }), h("span", { class: "meta", text: "최근 30일 · 지분 변동 신고 등 일상 보고는 뒤로" })]),
      feed(merge("disclosures", byRank), "최근 30일 공시 없음", x => `${fmt.md(x.date)}${x.filer ? " · " + x.filer : ""}`),
    ]),
  );
})();
