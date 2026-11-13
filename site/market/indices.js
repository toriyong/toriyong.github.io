// 증시 탭 상단: 주요 지수 카드 (국내 / 미국 / 아시아 / 통화) + 스파크라인
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);
  const box = $("indices");
  if (!box) return;

  let data;
  try {
    data = await loadJson("data/indices.json");
  } catch (e) {
    box.replaceChildren(h("p", { class: "meta", text: "지수 데이터는 다음 자동 수집 후 표시됩니다." }));
    return;
  }
  const groups = (data.groups || []).filter(g => (g.items || []).length);
  if (!groups.length) {
    box.replaceChildren(h("p", { class: "meta", text: "표시할 지수가 없습니다." }));
    return;
  }

  // 값 범위를 0~1 로 바꿔 폴리라인 좌표를 만든다 (SVG 100x32)
  function spark(points, up) {
    const n = points.length;
    if (n < 2) return null;
    const lo = Math.min(...points), hi = Math.max(...points), span = hi - lo || 1;
    const d = points.map((v, i) => `${(i / (n - 1) * 100).toFixed(1)},${(30 - (v - lo) / span * 28).toFixed(1)}`).join(" ");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 100 32");
    svg.setAttribute("class", `spark ${up === null ? "flat" : up ? "up" : "down"}`);
    svg.setAttribute("aria-hidden", "true");
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", d);
    svg.appendChild(line);
    return svg;
  }

  const fmtVal = v => v >= 1000 ? fmt.num(Math.round(v)) : fmt.num(v, 2);

  function card(x) {
    const up = x.rate === null || x.rate === undefined ? null : x.rate > 0 ? true : x.rate < 0 ? false : null;
    const cls = up === null ? "flat" : up ? "up" : "down";
    return h("div", { class: "idx-card" }, [
      h("div", { class: "idx-name", text: x.name }),
      h("div", { class: "idx-value", text: fmtVal(x.value) }),
      h("div", { class: `idx-diff ${cls}` }, [
        x.diff === null || x.diff === undefined ? null : h("span", { text: `${x.diff > 0 ? "+" : ""}${fmtVal(Math.abs(x.diff) >= 1000 ? x.diff : x.diff)}` }),
        x.rate === null || x.rate === undefined ? null : h("strong", { text: ` ${x.rate > 0 ? "▲" : x.rate < 0 ? "▼" : "–"} ${Math.abs(x.rate)}%` }),
      ]),
      spark(x.spark || [], up),
      h("div", { class: "meta idx-date", text: fmt.md(x.date) }),
    ]);
  }

  const tabs = h("div", { class: "idx-tabs", role: "tablist" });
  const panels = h("div", { class: "idx-panels" });
  groups.forEach((g, i) => {
    const panel = h("div", { class: `idx-row${i ? " hidden" : ""}`, role: "tabpanel" }, g.items.map(card));
    const btn = h("button", {
      type: "button", class: `idx-tab${i ? "" : " on"}`, role: "tab", "aria-selected": String(!i), text: g.name,
      onclick: () => {
        tabs.querySelectorAll(".idx-tab").forEach((b, j) => {
          b.classList.toggle("on", j === i);
          b.setAttribute("aria-selected", String(j === i));
        });
        panels.querySelectorAll(".idx-row").forEach((p, j) => p.classList.toggle("hidden", j !== i));
      },
    });
    tabs.appendChild(btn);
    panels.appendChild(panel);
  });

  box.replaceChildren(tabs, panels,
    h("p", { class: "meta", text: `국내 지수 출처 공공데이터포털(금융위원회), 해외 지수 출처 FRED · 전 영업일 종가 기준 · ${fmt.stamp(data.updated_at)} 수집` }));
})();
