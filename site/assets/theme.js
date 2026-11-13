// 테마(밝게/어둡게/시스템) — <head>에서 먼저 실행해 페이지가 깜빡이지 않게 한다.
(function () {
  "use strict";
  var KEY = "theme";
  var MODES = ["light", "dark", "system"];

  function read() {
    try {
      var v = localStorage.getItem(KEY);
      return MODES.indexOf(v) >= 0 ? v : "system";
    } catch (e) {
      return "system";                     // 저장소를 쓸 수 없는 환경이면 시스템 설정을 따름
    }
  }

  function apply(mode) {
    document.documentElement.setAttribute("data-theme", mode);
  }

  function set(mode) {
    if (MODES.indexOf(mode) < 0) return;
    apply(mode);
    try { localStorage.setItem(KEY, mode); } catch (e) { /* 저장 실패해도 화면에는 적용 */ }
    document.dispatchEvent(new CustomEvent("themechange", { detail: mode }));
  }

  apply(read());
  window.Theme = { get: read, set: set, modes: MODES };
})();
