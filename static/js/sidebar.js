/* Sidebar: icon-collapse on tablet, drawer + scrim on mobile. */
(function () {
  "use strict";

  var body = document.body;
  var toggle = document.querySelector("[data-sidebar-toggle]");
  var scrim = document.querySelector("[data-sidebar-scrim]");
  var KEY = "sidebar-collapsed";
  var MOBILE = window.matchMedia("(max-width: 720px)");

  function setDrawer(open) {
    body.dataset.drawer = open ? "1" : "0";
    if (scrim) {
      scrim.hidden = !open;
    }
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(open));
    }
  }

  function setCollapsed(collapsed) {
    body.dataset.collapsed = collapsed ? "1" : "0";
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch (error) {
      /* ignore */
    }
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(!collapsed));
    }
  }

  try {
    if (localStorage.getItem(KEY) === "1") {
      setCollapsed(true);
    }
  } catch (error) {
    /* ignore */
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      if (MOBILE.matches) {
        setDrawer(body.dataset.drawer !== "1");
      } else {
        setCollapsed(body.dataset.collapsed !== "1");
      }
    });
  }

  if (scrim) {
    scrim.addEventListener("click", function () {
      setDrawer(false);
    });
  }

  MOBILE.addEventListener("change", function (event) {
    if (event.matches) {
      setDrawer(false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setDrawer(false);
    }
  });
})();
