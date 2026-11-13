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
      h("td", { class: "name card-title" }, [h("a", { href: "#s-" + s.stock_code }, h("strong", { text: s.name })),
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

  // ---------- 종목별 뉴스 · 공시
  $("stocks").replaceChildren(...stocks.map(s => h("section", { class: "panel", id: "s-" + s.stock_code }, [
    h("div", { class: "panel-head" }, [
      h("h2", { text: s.name }),
      h("span", { class: "meta" }, [s.stock_code, " · ", ext(`https://finance.naver.com/item/main.naver?code=${s.stock_code}`, "시세"),
        ...(s.corp_code ? [" · ", ext(`https://dart.fss.or.kr/dsab007/main.do?autoSearch=Y&textCrpNm=${encodeURIComponent(s.name)}`, "DART")] : [])]),
    ]),
    h("div", { class: "grid-2" }, [
      h("div", null, [
        h("h3", { class: "sub-h", text: "최근 뉴스 (7일)" }),
        (s.news || []).length ? h("ul", { class: "feed compact" }, s.news.map(n => h("li", { class: "feed-item" }, [
          h("div", { class: "feed-meta" }, [n.source ? h("span", { class: "src", text: n.source }) : null, h("span", { class: "meta", text: fmt.md(n.date) })]),
          h("a", { class: "feed-title", href: n.url, target: "_blank", rel: "noopener noreferrer", text: n.title }),
        ]))) : h("p", { class: "meta", text: "최근 7일 뉴스 없음" }),
      ]),
      h("div", null, [
        h("h3", { class: "sub-h", text: "DART 공시 (30일)" }),
        (s.disclosures || []).length ? h("ul", { class: "feed compact" }, s.disclosures.map(d => h("li", { class: "feed-item" }, [
          h("div", { class: "feed-meta" }, [h("span", { class: "meta", text: `${fmt.md(d.date)} · ${d.filer || ""}` })]),
          h("a", { class: "feed-title", href: d.url, target: "_blank", rel: "noopener noreferrer", text: d.title }),
        ]))) : h("p", { class: "meta", text: "최근 30일 공시 없음" }),
      ]),
    ]),
  ])));
})();
