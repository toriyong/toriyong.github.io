// 학습: D-day · 공부 스케줄 캘린더 · 시험 일정 (data.json)
(async function () {
  "use strict";
  const { h, fmt, todayKst, loadJson } = window.Hub;
  const $ = id => document.getElementById(id);
  const DONE = "study:done:";              // 완료 체크 localStorage 접두어
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 불가 환경 */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* noop */ } },
  };

  let data;
  try {
    data = await loadJson("data.json");
  } catch (e) {
    $("content").replaceChildren(h("p", { class: "meta", text: "아직 학습 데이터가 없습니다. 다음 자동 배포 후 표시됩니다." }));
    return;
  }
  show(data);

  // ------------------------------------------------------------------ 화면
  function show(data) {
    $("updated").textContent = `생성 ${fmt.stamp(data.updated_at)}`;
    render(data);
  }

  function render(data) {
    const today = todayKst();
    const exams = data.exams || [];
    const plan = data.plan || {};
    const content = data.content || {};      // 시험별 학습 단원 {eis: [...], eip: [...]}
    const examOf = id => exams.find(e => e.id === id);
    const roundOf = (e, r) => (e && e.rounds || []).find(x => String(x.round) === String(r));
    const first = v => Array.isArray(v) ? v[0] : v;
    const last = v => Array.isArray(v) ? v[v.length - 1] : v;
    const D = s => new Date(s + "T00:00:00Z");
    const iso = d => d.toISOString().slice(0, 10);
    const add = (s, n) => { const d = D(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
    const diff = (a, b) => Math.round((D(a) - D(b)) / 864e5);
    const dday = s => { const n = diff(s, today); return n === 0 ? "D-DAY" : n > 0 ? `D-${n}` : `D+${-n}`; };

    // 임시(추정) 일정 경고
    const est = exams.flatMap(e => (e.rounds || []).filter(r => r.estimated).map(r => `${e.name} ${r.round}`));
    if (est.length) {
      $("banner-est").textContent = `임시 일정: ${est.join(", ")} — 2026년 패턴으로 추정한 날짜입니다. 공고가 나오면 config/exams.yml 을 실제 날짜로 바꿔 주세요.`;
      $("banner-est").classList.remove("hidden");
    }

    // ---------- 일정 이벤트
    const LABEL = { written_apply: "필기 접수", written: "필기", written_result: "필기 발표",
      practical_apply: "실기 접수", practical: "실기", final_result: "최종 발표" };
    const events = [];   // {date, end, exam, round, kind}
    for (const e of exams) for (const r of e.rounds || []) {
      for (const k of Object.keys(LABEL)) if (r[k]) events.push({ date: first(r[k]), end: last(r[k]), exam: e, round: r, kind: k });
    }

    // ---------- 목표 시험 → 공부 구간
    const targets = (plan.targets || []).map(t => {
      const e = examOf(t.exam), r = roundOf(e, t.round);
      return e && r ? { ...t, e, r } : null;
    }).filter(Boolean);
    const restSet = new Set((plan.rest_days || []).map(s => ["sun", "mon", "tue", "wed", "thu", "fri", "sat"].indexOf(s)));
    const hours = plan.hours || { weekday: 1, weekend: 2 };
    const start = plan.start || today;
    const segs = [];   // {from, to, phases, exam, round, label}
    for (const t of targets) {
      const wStart = first(t.r.written), pStart = first(t.r.practical);
      if (t.from === "written" && wStart) {
        segs.push({ from: start, to: add(wStart, -1), phases: plan.phases?.written || [], t, stage: "필기" });
        const after = t.r.written_result ? add(t.r.written_result, 0) : add(last(t.r.written), 1);
        if (pStart) segs.push({ from: after, to: add(pStart, -1), phases: plan.phases?.practical || [], t, stage: "실기" });
      } else if (pStart) {
        segs.push({ from: start, to: add(pStart, -1), phases: plan.phases?.practical || [], t, stage: "실기" });
      }
      // 시험 직전 N일(기본 14일)은 기출문제 풀이로 고정하고, 그 앞 기간만 단계 비중대로 나눈다
      const lastSeg = segs[segs.length - 1];
      const pastDays = plan.past_days ?? 14;
      if (lastSeg && lastSeg.t === t && pastDays > 0 && diff(lastSeg.to, lastSeg.from) + 1 > pastDays) {
        const pastFrom = add(lastSeg.to, -(pastDays - 1));
        segs.push({ from: pastFrom, to: lastSeg.to, phases: [{ name: "기출 풀이", kind: "past", weight: 1 }], t, stage: lastSeg.stage });
        lastSeg.to = add(pastFrom, -1);
      }
    }
    // 구간을 단계 비중대로 나눠 날짜별 과제 만들기
    const tasks = {};    // date → [{id, text, exam}]
    // 주말(토·일)은 그 주에 공부한 단원을 복습하는 한 묶음으로 만든다 (기출 풀이 기간은 제외)
    const weekendReview = plan.weekend_review ?? true;
    const weeks = {};    // `${exam}|${토요일}` → {s, sat, days:[토,일], units:[id]}
    const weekOf = (s, day) => {
      const dow = D(day).getUTCDay();
      const sat = add(day, dow === 0 ? -1 : 6 - dow);
      const k = `${s.t.exam}|${sat}`;
      return weeks[k] = weeks[k] || { s, sat, days: [], units: [] };
    };
    for (const s of segs) {
      const total = diff(s.to, s.from) + 1;
      if (total <= 0) continue;
      const wsum = s.phases.reduce((a, p) => a + (p.weight || 1), 0) || 1;
      let cursor = 0;
      s.phases.forEach((p, i) => {
        const len = i === s.phases.length - 1 ? total - cursor : Math.round(total * (p.weight || 1) / wsum);
        const kind = p.kind || (i === 0 ? "concept" : i === s.phases.length - 1 ? "review" : "quiz");
        // 이 단계의 공부일(쉬는 요일 제외)을 먼저 모은 뒤, 단원을 순서대로 고르게 배정
        const days = [];
        for (let k = 0; k < len; k++) {
          const day = add(s.from, cursor + k);
          const dow = D(day).getUTCDay();
          if (weekendReview && kind !== "past" && (dow === 0 || dow === 6)) weekOf(s, day).days.push(day);
          else if (!restSet.has(dow)) days.push(day);
        }
        const units = (content[s.t.exam] || []);
        days.forEach((day, n) => {
          const dow = D(day).getUTCDay();
          const hr = dow === 0 || dow === 6 ? hours.weekend : hours.weekday;
          const u = units.length && kind !== "review" && kind !== "past" ? units[Math.min(units.length - 1, Math.floor(n * units.length / days.length))] : null;
          const no = u ? u.id.split("-")[1] : "";
          if (u && weekendReview) { const w = weekOf(s, day); if (!w.units.includes(u.id)) w.units.push(u.id); }
          (tasks[day] = tasks[day] || []).push({
            id: `${day}:${s.t.exam}:${s.stage}`, exam: s.t.e.name, cls: `x-${s.t.exam}`, hr,
            text: u ? `${p.name} ${no} ${u.title}` : kind === "past" ? `기출 풀이 ${n + 1}일차` : `${p.name} · 전체 문제 점검`,
            href: u ? `unit/?u=${u.id}${kind === "quiz" ? "&mode=quiz" : ""}`
              : kind === "past" ? `unit/?e=${s.t.exam}&mode=past&d=${n + 1}&of=${days.length}&date=${day}` : `unit/?e=${s.t.exam}&mode=all`,
          });
        });
        cursor += len;
      });
    }
    for (const w of Object.values(weeks)) {
      if (!w.days.length) continue;            // 주말이 기출 풀이 기간이면 복습 과제 없음
      const exam = w.s.t.exam, nos = w.units.map(id => id.split("-")[1]);
      const task = {
        id: `${w.sat}:${exam}:주간복습`, exam: w.s.t.e.name, cls: `x-${exam} wk`, hr: hours.weekend,
        text: nos.length ? `주간 복습(토·일) ${nos[0]}${nos.length > 1 ? "~" + nos[nos.length - 1] : ""}` : "주간 복습(토·일) · 전체 문제 점검",
        href: nos.length ? `unit/?e=${exam}&mode=week&ids=${w.units.join(",")}&w=${w.sat}` : `unit/?e=${exam}&mode=all`,
      };
      for (const day of w.days) (tasks[day] = tasks[day] || []).push(task);   // 토·일 같은 과제(체크 하나로 공유)
    }
    // 시험별 과제 목록 — 토·일에 같이 걸린 주간 복습은 1건으로 센다
    const tasksOf = t => [...new Map(Object.values(tasks).flat().filter(x => x.id.includes(`:${t.exam}:`)).map(x => [x.id, x])).values()];
    const isDone = id => store.get(DONE + id) === "1";
    const SHORT = name => ({ 정보보안기사: "보안", 정보처리기사: "정처" }[name] || name.slice(0, 2));

    // ---------- D-day 카드: 목표 시험의 다음 일정
    const upcoming = targets.flatMap(t => events.filter(ev => ev.exam.id === t.e.id && String(ev.round.round) === String(t.r.round)
      && (ev.end || ev.date) >= today && (t.from === "written" || ev.kind.startsWith("practical") || ev.kind === "final_result")));
    upcoming.sort((a, b) => a.date.localeCompare(b.date));
    const key = new Set();
    const cards = upcoming.filter(ev => { const k = ev.exam.id + ev.round.round; if (key.has(k)) return false; key.add(k); return true; });
    const examDay = t => first(t.from === "written" ? t.r.written : t.r.practical);
    $("dday").replaceChildren(...(targets.length ? targets.map(t => {
      const next = cards.find(c => c.exam.id === t.e.id);
      const all = tasksOf(t);
      const done = all.filter(x => isDone(x.id)).length;
      return h("div", { class: `dday x-${t.exam}` }, [
        h("div", { class: "dday-head" }, [h("strong", { text: `${t.e.name} ${t.r.round}` }),
          t.r.estimated ? h("span", { class: "badge sev-medium", text: "임시" }) : null]),
        h("div", { class: "dday-big", text: dday(examDay(t)) }),
        h("div", { class: "meta", text: `${t.from === "written" ? "필기" : "실기"} ${fmt.md(examDay(t))}` }),
        next ? h("div", { class: "dday-next", text: `다음: ${LABEL[next.kind]} ${fmt.period(next.date, next.end)} (${dday(next.date)})` }) : null,
        h("div", { class: "bar" }, h("span", { class: "bar-fill", "data-w": all.length ? Math.round(done / all.length * 100) : 0 })),
        h("div", { class: "meta", text: `공부 진행 ${done}/${all.length}건` }),
      ]);
    }) : [h("p", { class: "meta", text: "목표 시험이 없습니다 (STUDY_PLAN targets)" })]));
    setBars();

    // ---------- 캘린더 (월~일)
    let [cy, cm] = today.slice(0, 7).split("-").map(Number);
    const evByDay = {};
    for (const ev of events) {
      // 기간 일정은 시작·끝만 표시(CBT 기간은 길어서 매일 표시하면 복잡함)
      evByDay[ev.date] = (evByDay[ev.date] || []).concat(ev);
      if (ev.end && ev.end !== ev.date) evByDay[ev.end] = (evByDay[ev.end] || []).concat({ ...ev, isEnd: true });
    }
    const evText = ev => `${ev.exam.name.replace("정보", "").replace("기사", "기")} ${LABEL[ev.kind]}${ev.end !== ev.date ? (ev.isEnd ? " 끝" : " 시작") : ""}`;

    function cellChildren(key) {
      return [
        ...(evByDay[key] || []).map(ev => h("span", { class: `ev exam x-${ev.exam.id}`, title: `${ev.exam.name} ${ev.round.round} ${LABEL[ev.kind]}`, text: evText(ev) })),
        ...(tasks[key] || []).map(t => h("span", { class: `task ${t.cls}${isDone(t.id) ? " done" : ""}` }, [
          h("button", { type: "button", class: "chk", title: "완료 체크", "aria-pressed": String(isDone(t.id)), "aria-label": `${t.text} 완료 체크`,
            onclick: () => { isDone(t.id) ? store.del(DONE + t.id) : store.set(DONE + t.id, "1"); renderCal(); render2(); },
            text: isDone(t.id) ? "✔" : "○" }),
          h("a", { class: "task-link", href: t.href, title: `${t.exam} ${t.text} (${t.hr}시간) — 눌러서 공부하기`, text: `[${SHORT(t.exam)}] ${t.text}` }),
        ])),
      ];
    }
    function renderCal() {
      $("cal-title").textContent = `${cy}년 ${cm}월`;
      const firstD = new Date(Date.UTC(cy, cm - 1, 1));
      const lastD = new Date(Date.UTC(cy, cm, 0));
      const s = new Date(firstD); s.setUTCDate(s.getUTCDate() - ((firstD.getUTCDay() + 6) % 7));
      const e = new Date(lastD); e.setUTCDate(e.getUTCDate() + (7 - ((lastD.getUTCDay() + 6) % 7) - 1));
      const cells = ["월", "화", "수", "목", "금", "토", "일"].map(d => h("div", { class: "cal-dow", text: d }));
      for (let d = new Date(s); d <= e; d.setUTCDate(d.getUTCDate() + 1)) {
        const k = iso(d);
        cells.push(h("div", { class: ["cal-day", d.getUTCMonth() !== cm - 1 ? "out" : "", k === today ? "today" : "", d.getUTCDay() % 6 === 0 ? "wkend" : ""].join(" ").trim() },
          [h("div", { class: "cal-date", text: d.getUTCDate() }), ...cellChildren(k)]));
      }
      $("calendar").replaceChildren(...cells);
      // 모바일 아젠다
      const prefix = `${cy}-${String(cm).padStart(2, "0")}`;
      const days = [...new Set([...Object.keys(tasks), ...Object.keys(evByDay)])].filter(k => k.startsWith(prefix)).sort();
      const DOW = ["일", "월", "화", "수", "목", "금", "토"];
      $("agenda").replaceChildren(...(days.length ? days.map(k => h("li", { class: "agenda-day" + (k === today ? " today" : "") }, [
        h("div", { class: "agenda-date" }, [h("strong", { text: D(k).getUTCDate() }), h("span", { text: DOW[D(k).getUTCDay()] })]),
        h("div", { class: "agenda-evs" }, cellChildren(k)),
      ])) : [h("li", { class: "empty", text: "이번 달 일정이 없습니다" })]));
    }
    function render2() {
      // 진행률만 다시 계산
      const rows = targets.map(t => {
        const all = tasksOf(t);
        const past = all.filter(x => x.id.slice(0, 10) <= today);
        const done = all.filter(x => isDone(x.id)).length;
        return h("span", { class: `chip x-${t.exam}` }, [`${t.e.name} `, h("strong", { text: `${done}/${past.length}` }), h("span", { class: "meta", text: " (오늘까지 계획 대비)" })]);
      });
      $("progress").replaceChildren(...rows);
      document.querySelectorAll(".dday").forEach((card, i) => {
        const t = targets[i]; if (!t) return;
        const all = tasksOf(t);
        const done = all.filter(x => isDone(x.id)).length;
        card.querySelector(".bar-fill").dataset.w = all.length ? Math.round(done / all.length * 100) : 0;
        card.lastChild.textContent = `공부 진행 ${done}/${all.length}건`;
      });
      setBars();
    }
    $("cal-prev").onclick = () => { cm--; if (cm < 1) { cm = 12; cy--; } renderCal(); };
    $("cal-next").onclick = () => { cm++; if (cm > 12) { cm = 1; cy++; } renderCal(); };
    $("cal-today").onclick = () => { [cy, cm] = today.slice(0, 7).split("-").map(Number); renderCal(); };
    renderCal();
    render2();

    // ---------- 시험 일정 표
    $("exams").replaceChildren(...exams.map(e => h("div", { class: "exam-block" }, [
      h("h3", { class: "sub-h" }, [e.name, " ", h("a", { href: e.url, target: "_blank", rel: "noopener noreferrer", class: "meta", text: e.org })]),
      h("div", { class: "table-wrap" }, h("table", { class: "rcards" }, [
        h("thead", null, h("tr", null, ["회차", ...Object.values(LABEL)].map(x => h("th", { text: x })))),
        h("tbody", null, (e.rounds || []).map(r => h("tr", null, [
          h("td", { class: "card-title" }, [h("strong", { text: r.round }), r.estimated ? h("span", { class: "badge sev-medium", text: " 임시" }) : null]),
          ...Object.entries(LABEL).map(([k, lab]) => h("td", { "data-label": lab, class: (last(r[k]) || "") < today ? "meta" : null, text: r[k] ? fmt.period(first(r[k]), last(r[k])) : "–" })),
        ]))),
      ])),
    ])));
  }

  function setBars() {
    document.querySelectorAll(".bar-fill").forEach(el => { el.style.width = (el.dataset.w || 0) + "%"; });
  }
})();
