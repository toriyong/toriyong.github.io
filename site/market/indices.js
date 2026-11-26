// 증시 탭 상단: 지수 보드 (국내가 위, 미국이 아래) — 네이버 증시 상단 배치를 따른다.
// 큰 카드: 당일 5분봉 차트 + 전일·고가·저가·52주 / 작은 칸: 현재가·등락·52주 최고
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const box = document.getElementById("indices");
  if (!box) return;
  const meta = document.getElementById("indices-meta");
  const NS = "http://www.w3.org/2000/svg";

  let data;
  try {
    data = await loadJson("data/indices.json");
  } catch (e) {
    box.replaceChildren(h("p", { class: "meta", text: "지수 데이터는 다음 자동 수집 후 표시됩니다." }));
    return;
  }
  const sections = (data.sections || []).filter(s => (s.main || []).length + (s.sub || []).length);
  if (!sections.length) {
    box.replaceChildren(h("p", { class: "meta", text: "표시할 지수가 없습니다. 다음 자동 수집을 기다려 주세요." }));
    return;
  }

  const n2 = v => (v === null || v === undefined ? "–" : Number(v).toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const dir = x => (x.diff > 0 ? "up" : x.diff < 0 ? "down" : "flat");
  const arrow = x => (x.diff > 0 ? "▲" : x.diff < 0 ? "▼" : "");
  const change = x => (x.diff === null || x.diff === undefined
    ? "–"
    : `${arrow(x)} ${n2(Math.abs(x.diff))} (${x.rate > 0 ? "+" : ""}${n2(x.rate)}%)`);
  // 시각은 각 거래소 현지 시각으로 (국내 KST, 미국 ET)
  const hhmm = (epoch, off) => {
    const d = new Date((epoch + off) * 1000);
    return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
  };
  const kstStamp = iso => {
    if (!iso) return "";
    const [d, t] = iso.split("T");
    return `${fmt.md(d)} ${t.slice(0, 5)}`;
  };
  const stateBadge = x => h("span", { class: `idx-state ${x.state === "open" ? "open" : ""}`, text: x.state === "open" ? "장중" : "장마감" });

  function svgEl(tag, attrs) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  }

  // 당일 차트: 영역 채움 + 전일 종가 점선 + 오른쪽 값 눈금 + 아래 시각 눈금
  function chart(x) {
    const pts = x.points || [];
    if (pts.length < 2) return h("div", { class: "idx-chart empty meta", text: "차트 데이터 없음" });
    const vals = pts.map(p => p[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (x.prev !== null && x.prev !== undefined) { lo = Math.min(lo, x.prev); hi = Math.max(hi, x.prev); }
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const W = 300, H = 90;
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0], span = t1 - t0 || 1;
    const X = t => ((t - t0) / span * W).toFixed(1);
    const Y = v => (H - (v - lo) / (hi - lo) * H).toFixed(1);
    const line = pts.map(p => `${X(p[0])},${Y(p[1])}`).join(" ");
    const cls = dir(x);

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", class: `idx-svg ${cls}`, "aria-hidden": "true" });
    svg.append(svgEl("polygon", { class: "area", points: `0,${H} ${line} ${X(t1)},${H}` }));
    if (x.prev !== null && x.prev !== undefined) {
      svg.append(svgEl("line", { class: "base", x1: 0, x2: W, y1: Y(x.prev), y2: Y(x.prev) }));
    }
    svg.append(svgEl("polyline", { class: "line", points: line }));

    const ticks = [];
    const step = Math.max(1, Math.floor(pts.length / 3));
    for (let i = step; i < pts.length - step / 2; i += step) ticks.push(pts[i][0]);
    // 오른쪽 눈금: 당일 최고·중간·최저를 실제 높이에 맞춰 놓는다 (CSP 때문에 style 대신 CSSOM 사용)
    const realHi = Math.max(...vals), realLo = Math.min(...vals);
    const yLabel = v => {
      const el = h("span", { text: n2(v) });
      el.style.top = `${(Number(Y(v)) / H * 100).toFixed(1)}%`;
      return el;
    };
    return h("div", { class: "idx-chart" }, [
      h("div", { class: "idx-plot" }, [svg,
        h("div", { class: "idx-x" }, ticks.map(t => h("span", { class: "meta", text: hhmm(t, x.tz_offset || 0) })))]),
      h("div", { class: "idx-y meta" }, [yLabel(realHi), yLabel((realHi + realLo) / 2), yLabel(realLo)]),
    ]);
  }

  const stat = (label, v, cls) => h("div", { class: "idx-stat" }, [
    h("span", { class: "meta", text: label }), h("span", { class: cls || null, text: n2(v) }),
  ]);

  function mainCard(x) {
    const hiCls = x.prev && x.high > x.prev ? "up" : x.prev && x.high < x.prev ? "down" : "";
    const loCls = x.prev && x.low > x.prev ? "up" : x.prev && x.low < x.prev ? "down" : "";
    return h("article", { class: `idx-main${x.stale ? " stale" : ""}` }, [
      h("div", { class: "idx-head" }, [h("strong", { text: x.name }), stateBadge(x)]),
      h("div", { class: "idx-now" }, [
        h("span", { class: "idx-big", text: n2(x.value) }),
        h("span", { class: `idx-chg ${dir(x)}`, text: change(x) }),
      ]),
      chart(x),
      h("div", { class: "idx-stats" }, [
        stat("전일", x.prev), stat("고가", x.high, hiCls), stat("저가", x.low, loCls),
        stat("52주 최고", x.w52h), stat("52주 최저", x.w52l),
        h("div", { class: "idx-stat" }, [h("span", { class: "meta", text: "기준" }), h("span", { class: "meta", text: kstStamp(x.time) })]),
      ]),
    ]);
  }

  function subTile(x) {
    return h("div", { class: `idx-tile${x.stale ? " stale" : ""}` }, [
      h("div", { class: "idx-head" }, [h("span", { text: x.name }), h("i", { class: `dot ${x.state === "open" ? "open" : ""}`, title: x.state === "open" ? "거래 중" : "장마감" })]),
      h("div", { class: "idx-tval", text: n2(x.value) }),
      h("div", { class: `idx-tchg ${dir(x)}`, text: change(x) }),
      h("div", { class: "meta idx-t52", text: x.w52h ? `52주 최고 ${n2(x.w52h)}` : "" }),
    ]);
  }

  const rows = sections.map(s => {
    const lead = (s.main || [])[0] || (s.sub || [])[0];
    const open = (s.main || []).some(x => x.state === "open");
    return h("section", { class: "idx-section" }, [
      h("div", { class: "idx-section-head" }, [
        h("h3", { text: s.name }),
        h("span", { class: `idx-state ${open ? "open" : ""}`, text: open ? "장중" : "장마감" }),
        h("span", { class: "meta", text: lead ? `${kstStamp(lead.time)} 기준 (한국 시각)` : "" }),
      ]),
      h("div", { class: `idx-board cols-${(s.main || []).length + ((s.sub || []).length ? 1 : 0)}` }, [
        ...(s.main || []).map(mainCard),
        (s.sub || []).length ? h("div", { class: "idx-subs" }, s.sub.map(subTile)) : null,
      ]),
    ]);
  });

  const stale = sections.some(s => [...(s.main || []), ...(s.sub || [])].some(x => x.stale));
  box.replaceChildren(...rows,
    h("p", { class: "meta idx-foot", text:
      `출처 ${data.source || "Yahoo Finance"} · 국내 시세는 약 20분 지연될 수 있음 · ${fmt.stamp(data.updated_at)} 수집` +
      (stale ? " · 흐리게 표시된 항목은 이번 수집에 실패해 직전 값을 보여 줍니다" : "") }));
  if (meta) meta.textContent = "";
})();
