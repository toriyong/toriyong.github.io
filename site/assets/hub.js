// 허브: 증시 카드에 공모주 요약 표시
(async function () {
  "use strict";
  const { h, fmt, todayKst, loadJson } = window.Hub;
  const box = document.getElementById("market-stat");
  try {
    const data = await loadJson("market/data/ipo.json");
    const items = (data.items || []).filter(i => i.grade !== "spac");
    const today = todayKst();
    const subscribing = items.filter(i => i.status === "subscribing");
    const next = items.find(i => i.sub_start && i.sub_start > today);
    box.replaceChildren(
      h("div", null, ["청약 중 ", h("strong", { text: `${subscribing.length}건` }),
        " · 예정 ", h("strong", { text: `${items.filter(i => i.status === "upcoming").length}건` })]),
      h("div", null, next ? ["다음 청약: ", h("strong", { text: next.corp_name }), ` (${fmt.md(next.sub_start)})`] : "예정된 청약 없음"),
      h("div", null, `기준 ${fmt.stamp(data.updated_at)}${data.sample ? " · 예시 데이터" : ""}`),
    );
  } catch (e) {
    box.textContent = "아직 수집된 데이터가 없습니다";
  }
})();

// 허브: 보안·인프라 카드 요약
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const box = document.getElementById("sec-stat");
  if (!box) return;
  try {
    const d = await loadJson("security/data/secinfra.json");
    const s = d.summary || {};
    const top = (d.news || []).find(n => n.id === (d.top || [])[0]);
    const ms = (d.patches || []).find(p => p.name.startsWith("Microsoft"));
    box.replaceChildren(
      h("div", null, ["Critical ", h("strong", { text: `${s.critical ?? 0}건` }),
        " · 실제 악용 취약점 ", h("strong", { text: `${s.kev_recent ?? 0}건` })]),
      h("div", { class: "clip" }, top ? ["주요: ", h("strong", { text: top.title })] : "주요 이슈 없음"),
      h("div", null, `${ms ? `MS 패치 D-${ms.d_day} · ` : ""}기준 ${fmt.stamp(d.updated_at)}${d.sample ? " · 예시 데이터" : ""}`),
    );
  } catch (e) {
    box.textContent = "아직 수집된 데이터가 없습니다";
  }
})();
