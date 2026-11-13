// 학습 단원: ?u=단원id (&mode=quiz) · ?e=시험id&mode=all(전체 문제) · 매개변수 없으면 단원 목록
(async function () {
  "use strict";
  const { h, loadJson } = window.Hub;
  const box = document.getElementById("unit");
  const q = new URLSearchParams(location.search);
  const NAME = { eis: "정보보안기사 실기", eip: "정보처리기사 실기" };
  const DONE = "study:unit:";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* noop */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* noop */ } },
  };

  let data;
  try {
    data = await loadJson("../data.json");
  } catch (e) {
    box.replaceChildren(h("p", { class: "meta", text: "학습 데이터를 불러오지 못했습니다." }));
    return;
  }
  const content = data.content || {};
  const all = Object.entries(content).flatMap(([exam, units]) => units.map((u, i) => ({ ...u, exam, idx: i })));

  const quizItem = (z, n) => h("li", { class: "quiz" }, [
    h("p", { class: "quiz-q" }, [h("span", { class: "quiz-n", text: `Q${n}` }), z.q]),
    z.code ? h("pre", { class: "code" }, h("code", { text: z.code.replace(/\n$/, "") })) : null,
    h("details", { class: "quiz-a" }, [h("summary", { text: "정답 보기" }), h("p", { text: z.a })]),
  ]);
  const toggleAll = open => document.querySelectorAll("details.quiz-a").forEach(d => { d.open = open; });
  const tools = () => h("div", { class: "unit-tools" }, [
    h("button", { type: "button", class: "more", text: "정답 모두 펼치기", onclick: () => toggleAll(true) }),
    h("button", { type: "button", class: "more", text: "모두 접기", onclick: () => toggleAll(false) }),
  ]);

  // ---------- 전체 문제 점검
  if (q.get("mode") === "all" && content[q.get("e")]) {
    const exam = q.get("e");
    let n = 0;
    document.title = `${NAME[exam]} 전체 문제 · toriyong`;
    box.replaceChildren(
      h("h1", { text: `${NAME[exam] || exam} · 전체 문제 점검` }),
      h("p", { class: "lead", text: "답을 가리고 먼저 써 본 뒤 정답을 확인하세요. 틀린 문제는 해당 단원으로 돌아가 다시 봅니다." }),
      tools(),
      ...content[exam].map(u => h("section", { class: "panel" }, [
        h("h2", null, h("a", { href: `?u=${u.id}`, text: `${u.id.split("-")[1]} ${u.title}` })),
        h("ol", { class: "quiz-list" }, (u.quiz || []).map(z => quizItem(z, ++n))),
      ])),
    );
    return;
  }

  // ---------- 단원 보기
  const u = all.find(x => x.id === q.get("u"));
  if (u) {
    const list = content[u.exam];
    const prev = list[u.idx - 1], next = list[u.idx + 1];
    const quizFirst = q.get("mode") === "quiz";
    const done = () => store.get(DONE + u.id) === "1";
    document.title = `${u.title} · 학습 · toriyong`;
    const points = h("section", { class: "panel" }, [
      h("h2", { text: "핵심 정리" }),
      quizFirst ? h("details", null, [h("summary", { text: "핵심 정리 펼치기 (문제를 먼저 풀어 보세요)" }), h("ul", { class: "points" }, u.points.map(p => h("li", { text: p })))])
                : h("ul", { class: "points" }, u.points.map(p => h("li", { text: p }))),
    ]);
    const quiz = h("section", { class: "panel" }, [
      h("div", { class: "panel-head" }, [h("h2", { text: "연습문제" }), tools()]),
      h("ol", { class: "quiz-list" }, (u.quiz || []).map((z, i) => quizItem(z, i + 1))),
    ]);
    const doneBtn = h("button", { type: "button", class: "more" });
    const paint = () => { doneBtn.textContent = done() ? "✔ 이 단원 학습 완료 (취소)" : "이 단원 학습 완료로 표시"; };
    doneBtn.onclick = () => { done() ? store.del(DONE + u.id) : store.set(DONE + u.id, "1"); paint(); };
    paint();
    box.replaceChildren(
      h("p", { class: "meta", text: `${NAME[u.exam] || u.exam} · ${u.idx + 1} / ${list.length} 단원${quizFirst ? " · 문제 풀이 모드" : ""}` }),
      h("h1", { text: u.title }),
      ...(quizFirst ? [quiz, points] : [points, quiz]),
      h("div", { class: "unit-nav" }, [
        prev ? h("a", { href: `?u=${prev.id}`, text: `← ${prev.title}` }) : h("span"),
        doneBtn,
        next ? h("a", { href: `?u=${next.id}`, text: `${next.title} →` }) : h("span"),
      ]),
    );
    return;
  }

  // ---------- 단원 목록
  document.title = "학습 단원 · toriyong";
  box.replaceChildren(
    h("h1", { text: "학습 단원" }),
    h("p", { class: "lead", text: "단원을 누르면 핵심 정리와 연습문제가 열립니다." }),
    ...Object.entries(content).map(([exam, units]) => h("section", { class: "panel" }, [
      h("div", { class: "panel-head" }, [h("h2", { text: NAME[exam] || exam }), h("a", { href: `?e=${exam}&mode=all`, text: "전체 문제 점검 →" })]),
      h("ol", { class: "unit-list" }, units.map(x => h("li", null, [
        h("a", { href: `?u=${x.id}`, text: x.title }),
        h("span", { class: "meta", text: ` 정리 ${x.points.length} · 문제 ${(x.quiz || []).length}${store.get(DONE + x.id) === "1" ? " · ✔ 완료" : ""}` }),
      ]))),
    ])),
  );
})();
