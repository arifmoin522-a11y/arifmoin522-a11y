/* Halftone dot texture.
   Slow-moving dot grid; radius modulated by a drifting noise field.
   Parameters come from data-* attributes (spacing/radius/speed/opacity)
   or CSS custom properties; nothing is hardcoded per placement. */
(function () {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)");
  var CYCLE_MS = 1000 * 26; /* ~26 s loop, inside the required 20-30 s range */

  function readUnit(value, fallbackPx) {
    var parsed = parseFloat(value);
    return isNaN(parsed) ? fallbackPx : parsed;
  }

  function config(canvas) {
    var styles = getComputedStyle(canvas);
    return {
      spacing: readUnit(canvas.dataset.spacing || styles.getPropertyValue("--dot-spacing"), 22),
      radius: readUnit(canvas.dataset.radius || styles.getPropertyValue("--dot-radius"), 4.5),
      speed: readUnit(canvas.dataset.speed || styles.getPropertyValue("--dot-speed"), 20),
      opacity: readUnit(canvas.dataset.opacity || styles.getPropertyValue("--dot-opacity"), 0.45),
    };
  }

  function noise(x, y, t) {
    /* cheap smooth value noise: two drifting sine wells + gentle swirl */
    var slow = t / CYCLE_MS;
    var a = Math.sin(x * 0.012 + slow * Math.PI * 2) + Math.cos(y * 0.017 - slow * Math.PI * 2);
    var b = Math.cos((x + y) * 0.008 + slow * Math.PI);
    return (a * 0.5 + b * 0.5 + 2) / 4; /* stays within 0..1 */
  }

  function init(canvas) {
    var ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    var params = config(canvas);
    var start = performance.now();
    var frame = 0;

    function resize() {
      var ratio = window.devicePixelRatio || 1;
      var rect = canvas.getBoundingClientRect();
      canvas.width = Math.round(rect.width * ratio);
      canvas.height = Math.round(rect.height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function paint(now) {
      var elapsed = now - start;
      var slowFactor = params.speed > 0 ? params.speed / 20 : 1;
      var t = start + elapsed * slowFactor;
      var ink = getComputedStyle(canvas).color || "black";
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      var rect = canvas.getBoundingClientRect();
      var step = params.spacing * (rect.width < 560 ? 1.35 : 1); /* fewer dots on small screens */
      ctx.fillStyle = ink;
      ctx.globalAlpha = params.opacity;
      for (var x = step / 2; x < rect.width; x += step) {
        for (var y = step / 2; y < rect.height; y += step) {
          var n = noise(x, y, t);
          ctx.beginPath();
          ctx.arc(x, y, params.radius * n, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
    }

    function loop(now) {
      paint(now);
      frame = requestAnimationFrame(loop);
    }

    var resizeTimer;
    function onResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        resize();
        if (REDUCED.matches) {
          paint(performance.now());
        }
      }, 150);
    }

    function onVisibility() {
      if (document.hidden) {
        cancelAnimationFrame(frame);
      } else if (!REDUCED.matches) {
        loop(performance.now());
      }
    }

    function onReducedChange() {
      if (REDUCED.matches) {
        cancelAnimationFrame(frame);
        paint(performance.now()); /* one static frame */
      } else {
        loop(performance.now());
      }
    }

    resize();
    if (REDUCED.matches) {
      paint(performance.now());
    } else {
      loop(performance.now());
    }
    window.addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onVisibility);
    if (REDUCED.addEventListener) {
      REDUCED.addEventListener("change", onReducedChange);
    }
  }

  function setup() {
    document.querySelectorAll("canvas.halftone").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
