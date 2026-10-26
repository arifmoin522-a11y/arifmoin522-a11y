/* Theme toggle: persisted in localStorage, follows prefers-color-scheme. */
(function () {
  "use strict";

  var KEY = "theme";

  function currentTheme() {
    return document.documentElement.dataset.theme || "light";
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.setAttribute("aria-label", "Switch to " + (theme === "light" ? "dark" : "light") + " theme");
    });
    document.querySelectorAll("[data-icon-light]").forEach(function (el) {
      el.hidden = theme === "dark";
    });
    document.querySelectorAll("[data-icon-dark]").forEach(function (el) {
      el.hidden = theme !== "dark";
    });
  }

  function store(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (error) {
      /* storage unavailable (privacy mode); theme stays session-local */
    }
  }

  apply(currentTheme());

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-theme-toggle]");
    if (!button) {
      return;
    }
    var next = currentTheme() === "dark" ? "light" : "dark";
    apply(next);
    store(next);
  });
})();
