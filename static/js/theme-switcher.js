/* =========================================================
   EVENTRA - Theme Switcher (Light / Dark / System)
   Persists the chosen mode in localStorage. "system" resolves
   live against the OS color-scheme preference and keeps
   listening for changes while that mode is selected.
   ========================================================= */
(function () {
  "use strict";

  var STORAGE_KEY = "eventra-theme";
  var DEFAULT_MODE = "dark"; // matches the product's existing default chrome until Phase 2 navbar rework

  function getSavedMode() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) || DEFAULT_MODE;
    } catch (e) {
      return DEFAULT_MODE;
    }
  }

  function saveMode(mode) {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch (e) {
      /* localStorage unavailable (e.g. privacy mode) - preference just won't persist */
    }
  }

  function systemPrefersDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function resolvedTheme(mode) {
    if (mode === "system") return systemPrefersDark() ? "dark" : "light";
    return mode;
  }

  function applyMode(mode) {
    document.documentElement.setAttribute("data-theme", resolvedTheme(mode));
    document.querySelectorAll("[data-theme-option]").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-theme-option") === mode);
    });
    document.dispatchEvent(new CustomEvent("eventra:themechange", { detail: { mode: mode } }));
  }

  // Exposed for the navbar's Light/Dark/System buttons.
  window.setEventraTheme = function (mode) {
    applyMode(mode);
    saveMode(mode);
  };

  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      if (getSavedMode() === "system") applyMode("system");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    applyMode(getSavedMode());
  });
})();
