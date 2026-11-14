// 소개(포트폴리오) 페이지. 내용은 config/portfolio.yml 에서 빌드된 data.json 에서 읽는다.
(async function () {
  "use strict";
  const { h, fmt, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);
  const ISSUE = "https://github.com/toriyong/toriyong.github.io/issues/new";
  // /about/?edit=1 로 열면 자격증 옆에 편집 버튼이 나온다(남에게 보일 땐 숨김)
  const edit = new URLSearchParams(location.search).get("edit") === "1";

  function certHref(action, name, date) {
    const p = new URLSearchParams({ template: "cert.yml", title: `[자격증] ${name}`, action, name });
    if (date) p.set("date", date);
    return `${ISSUE}?${p.toString()}`;
  }
  const todayKstIso = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);

  let d;
  try {
    d = await loadJson("data.json");
  } catch (e) {
    $("pf-summary").textContent = "내용을 불러오지 못했습니다. 다음 배포 후 다시 열어 보세요.";
    return;
  }

  // ---------- 소개
  const p = d.profile || {};
  if (p.name) {
    $("pf-name").textContent = p.name;
    document.title = `${p.name} · 소개`;
  }
  $("pf-headline").textContent = p.headline || "";
  $("pf-summary").textContent = p.summary || "";
  $("pf-links").replaceChildren(...(p.links || []).map(l =>
    h("a", { class: "pf-link", href: l.url, target: "_blank", rel: "noopener noreferrer", text: l.label })));

  // ---------- 경력
  const career = d.career || [];
  $("pf-career-note").textContent = [d.career_total, career.length > 1 ? `${career.length}개사` : null].filter(Boolean).join(" · ");
  $("pf-career").replaceChildren(...career.map(c => h("article", { class: "pf-job" }, [
    h("div", { class: "pf-job-head" }, [
      h("div", null, [
        h("strong", { text: c.company }),
        h("span", { class: "pf-job-title", text: [c.team, c.title].filter(Boolean).join(" · ") }),
      ]),
      h("span", { class: "meta", text: c.period }),
    ]),
    h("ul", { class: "points" }, (c.points || []).map(t => h("li", { text: t }))),
  ])));

  // ---------- 보유 기술
  $("pf-skills").replaceChildren(...(d.skills || []).map(g => h("div", { class: "pf-skill-row" }, [
    h("div", { class: "pf-skill-group", text: g.group }),
    h("div", { class: "pf-chips" }, (g.items || []).map(i => h("span", { class: "pf-chip", text: i }))),
  ])));

  // ---------- 기술 노트 (주제 범위만)
  const nt = d.notes || {};
  if (!(nt.groups || []).length) $("pf-notes-panel").classList.add("hidden");
  else $("pf-notes").replaceChildren(
    nt.intro ? h("p", { class: "pf-notes-intro", text: nt.intro }) : null,
    h("div", null, (nt.groups || []).map(g => h("div", { class: "pf-skill-row" }, [
      h("div", { class: "pf-skill-group", text: g.name }),
      h("div", { class: "meta", text: g.items }),
    ]))));

  // ---------- 자격증
  const certs = d.certifications || [];
  const earned = certs.filter(c => c.status === "earned");
  const preparing = certs.filter(c => c.status !== "earned");
  $("pf-cert-note").textContent = `취득 ${earned.length} · 준비 중 ${preparing.length}`;

  function certRow(c) {
    const on = c.status === "earned";
    const when = c.date || c.year;
    const dday = c.exam_date ? Math.ceil((new Date(c.exam_date + "T00:00:00+09:00") - Date.now()) / 86400e3) : null;
    return h("li", { class: "pf-cert" }, [
      h("span", { class: `pf-badge ${on ? "on" : "prep"}`, text: on ? "취득" : "준비 중" }),
      h("div", { class: "pf-cert-main" }, [
        h("strong", { text: c.name }),
        h("span", { class: "meta" }, [
          [when, c.org, c.note].filter(Boolean).join(" · "),
          c.exam_date ? `${when || c.org || c.note ? " · " : ""}응시 예정 ${c.exam_date}${c.estimated ? " (공고 전 추정)" : ""}${dday !== null && dday >= 0 ? ` · D-${dday}` : ""}` : null,
        ]),
      ]),
      edit && !on ? h("div", { class: "pf-cert-act" }, [
        h("a", { class: "pf-btn on", href: certHref("합격", c.name, todayKstIso()), target: "_blank", rel: "noopener noreferrer",
                 title: `${c.name} 합격으로 변경`, text: "합격" }),
        h("a", { class: "pf-btn", href: certHref("응시 일정 변경", c.name, c.exam_date || ""), target: "_blank", rel: "noopener noreferrer",
                 title: `${c.name} 응시 예정일 변경`, text: "일정" }),
      ]) : null,
    ]);
  }
  $("pf-certs").replaceChildren(
    h("ul", { class: "pf-list" }, [...earned, ...preparing].map(certRow)),
    edit ? h("div", { class: "pf-edit-foot" }, [
      h("a", { class: "pf-btn", href: `${ISSUE}?template=cert.yml&action=%EC%B6%94%EA%B0%80`, target: "_blank", rel: "noopener noreferrer", text: "＋ 자격증 추가" }),
      h("span", { class: "meta", text: "버튼을 누르면 GitHub 이슈가 열리고, 제출하면 자동으로 PR 이 만들어집니다. 머지하면 반영됩니다." }),
    ]) : h("p", { class: "meta", text: "" }));

  // ---------- 학습 현황 (완료 체크가 아니라 커리큘럼 경과 기준)
  const s = d.study || {};
  const note = [];
  if (s.start) note.push(`${s.start} 시작`);
  if (s.weeks_total) note.push(`${s.weeks_total}주 과정`);
  $("pf-study-note").textContent = note.join(" · ");

  const rows = (s.targets || []).map(t => {
    const pct = s.weeks_total && s.week_now ? Math.min(100, Math.round(s.week_now / s.weeks_total * 100)) : 0;
    const bar = h("div", { class: "bar" }, h("div", { class: "bar-fill" }));
    const card = h("div", { class: "pf-study-card" }, [
      h("div", { class: "pf-study-top" }, [
        h("strong", { text: t.exam_name || t.exam }),
        h("span", { class: "meta", text: t.round ? `${t.round} 실기` : "" }),
      ]),
      h("div", { class: "meta" }, [
        t.exam_date ? `시험 ${t.exam_date}${t.estimated ? " (공고 전 추정)" : ""}` : "일정 미정",
        t.d_day !== null && t.d_day !== undefined ? ` · D-${t.d_day}` : null,
      ]),
      bar,
      h("div", { class: "meta", text: `${t.units ? `${t.units}개 단원` : ""}${s.started && s.week_now ? ` · ${s.week_now}주차 진행 중` : " · 시작 전"}` }),
    ]);
    bar.firstChild.style.width = `${pct}%`;
    return card;
  });
  $("pf-study").replaceChildren(
    rows.length ? h("div", { class: "pf-study-grid" }, rows) : h("p", { class: "meta", text: "준비 중인 시험이 없습니다." }),
    h("p", { class: "meta", text: "학습 단원과 일정은 학습 탭에서 자동으로 가져옵니다." }));

  // ---------- 주요 프로젝트
  $("pf-projects").replaceChildren(...(d.projects || []).map(x => h("article", { class: "pf-proj" }, [
    h("div", { class: "pf-proj-head" }, [
      x.url ? h("a", { href: x.url, target: "_blank", rel: "noopener noreferrer" }, h("strong", { text: x.title }))
            : h("strong", { text: x.title }),
      h("span", { class: "meta", text: [x.period, x.role].filter(Boolean).join(" · ") }),
    ]),
    h("p", { class: "pf-proj-sum", text: x.summary }),
    h("div", { class: "pf-chips" }, (x.stack || []).map(t => h("span", { class: "pf-chip sm", text: t }))),
  ])));

  // ---------- 교육·훈련
  const tr = d.training || [];
  if (!tr.length) $("pf-train-panel").classList.add("hidden");
  else $("pf-train").replaceChildren(h("ul", { class: "pf-list" }, tr.map(t => h("li", { class: "pf-cert" }, [
    h("div", { class: "pf-cert-main" }, [
      h("strong", { text: t.name }),
      h("span", { class: "meta", text: [t.org, t.period].filter(Boolean).join(" · ") }),
      t.note ? h("span", { class: "meta", text: t.note }) : null,
    ]),
  ]))));

  // ---------- 학력
  const edu = d.education || [];
  if (!edu.length) $("pf-edu-panel").classList.add("hidden");
  else $("pf-edu").replaceChildren(h("ul", { class: "pf-list" }, edu.map(e => h("li", { class: "pf-cert" }, [
    h("div", { class: "pf-cert-main" }, [
      h("strong", { text: e.school }),
      h("span", { class: "meta", text: [e.period, e.note].filter(Boolean).join(" · ") }),
    ]),
  ]))));
})();
