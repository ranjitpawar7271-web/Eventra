/* =========================================================
   EVENTRA - Advanced Theme Switcher
   ---------------------------------------------------------
   Supports:
   - Main Theme
   - Navbar Theme
   - Sidebar Theme
   - Font Family
   - Font Size
   - Persistent preferences using localStorage
   ========================================================= */

(function () {
  "use strict";

  /* =========================================================
     STORAGE KEYS
     ========================================================= */

  var THEME_KEY = "eventra-theme";
  var NAVBAR_KEY = "eventra-navbar-theme";
  var SIDEBAR_KEY = "eventra-sidebar-theme";
  var FONT_KEY = "eventra-font";
  var FONT_SIZE_KEY = "eventra-font-size";


  /* =========================================================
     DEFAULT VALUES
     ========================================================= */

  var DEFAULT_THEME = "dark";
  var DEFAULT_NAVBAR = "same";
  var DEFAULT_SIDEBAR = "same";
  var DEFAULT_FONT = "poppins";
  var DEFAULT_FONT_SIZE = "medium";


  /* =========================================================
     LOCAL STORAGE HELPERS
     ========================================================= */

  function getPreference(key, fallback) {
    try {
      return window.localStorage.getItem(key) || fallback;
    } catch (e) {
      return fallback;
    }
  }


  function savePreference(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      // Ignore storage errors.
    }
  }


  /* =========================================================
     MAIN THEME
     ========================================================= */

  function systemPrefersDark() {
    return (
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    );
  }


  function resolveMainTheme(theme) {

    if (theme === "system") {
      return systemPrefersDark() ? "dark" : "light";
    }

    return theme;
  }


  function applyMainTheme(theme) {

    var resolvedTheme = resolveMainTheme(theme);

    document.documentElement.setAttribute(
      "data-theme",
      resolvedTheme
    );

    document.documentElement.setAttribute(
      "data-theme-mode",
      theme
    );

    updateActiveOptions(
      "[data-theme-option]",
      theme
    );
  }


  /* =========================================================
     NAVBAR THEME
     ========================================================= */

  function applyNavbarTheme(theme) {

    document.documentElement.setAttribute(
      "data-navbar-theme",
      theme
    );

    updateActiveOptions(
      "[data-navbar-option]",
      theme
    );
  }


  /* =========================================================
     SIDEBAR THEME
     ========================================================= */

  function applySidebarTheme(theme) {

    document.documentElement.setAttribute(
      "data-sidebar-theme",
      theme
    );

    updateActiveOptions(
      "[data-sidebar-option]",
      theme
    );
  }


  /* =========================================================
     FONT FAMILY
     ========================================================= */

  var FONT_MAP = {
    poppins:
      "'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",

    inter:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",

    roboto:
      "'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",

    montserrat:
      "'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",

    opensans:
      "'Open Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",

    system:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  };


  function applyFont(font) {

    var fontFamily =
      FONT_MAP[font] || FONT_MAP[DEFAULT_FONT];

    document.documentElement.style.setProperty(
      "--eventra-font-family",
      fontFamily
    );

    document.documentElement.setAttribute(
      "data-font",
      font
    );

    updateActiveOptions(
      "[data-font-option]",
      font
    );
  }


  /* =========================================================
     FONT SIZE
     ========================================================= */

  var FONT_SIZE_MAP = {
    small: "0.92",
    medium: "1",
    large: "1.08"
  };


  function applyFontSize(size) {

    var scale =
      FONT_SIZE_MAP[size] ||
      FONT_SIZE_MAP[DEFAULT_FONT_SIZE];

    document.documentElement.style.setProperty(
      "--eventra-font-scale",
      scale
    );

    document.documentElement.setAttribute(
      "data-font-size",
      size
    );

    updateActiveOptions(
      "[data-font-size-option]",
      size
    );
  }


  /* =========================================================
     ACTIVE OPTION HANDLER
     ========================================================= */

  function updateActiveOptions(selector, value) {

    document
      .querySelectorAll(selector)
      .forEach(function (element) {

        element.classList.toggle(
          "active",
          element.getAttribute(
            element.hasAttribute("data-theme-option")
              ? "data-theme-option"
              : element.hasAttribute("data-navbar-option")
              ? "data-navbar-option"
              : element.hasAttribute("data-sidebar-option")
              ? "data-sidebar-option"
              : element.hasAttribute("data-font-option")
              ? "data-font-option"
              : "data-font-size-option"
          ) === value
        );

      });
  }


  /* =========================================================
     PUBLIC API
     ========================================================= */

  window.setEventraTheme = function (theme) {

    applyMainTheme(theme);

    savePreference(
      THEME_KEY,
      theme
    );

    dispatchThemeChange();
  };


  window.setEventraNavbarTheme = function (theme) {

    applyNavbarTheme(theme);

    savePreference(
      NAVBAR_KEY,
      theme
    );

    dispatchThemeChange();
  };


  window.setEventraSidebarTheme = function (theme) {

    applySidebarTheme(theme);

    savePreference(
      SIDEBAR_KEY,
      theme
    );

    dispatchThemeChange();
  };


  window.setEventraFont = function (font) {

    applyFont(font);

    savePreference(
      FONT_KEY,
      font
    );

    dispatchThemeChange();
  };


  window.setEventraFontSize = function (size) {

    applyFontSize(size);

    savePreference(
      FONT_SIZE_KEY,
      size
    );

    dispatchThemeChange();
  };


  /* =========================================================
     RESET ALL SETTINGS
     ========================================================= */

  window.resetEventraAppearance = function () {

    savePreference(
      THEME_KEY,
      DEFAULT_THEME
    );

    savePreference(
      NAVBAR_KEY,
      DEFAULT_NAVBAR
    );

    savePreference(
      SIDEBAR_KEY,
      DEFAULT_SIDEBAR
    );

    savePreference(
      FONT_KEY,
      DEFAULT_FONT
    );

    savePreference(
      FONT_SIZE_KEY,
      DEFAULT_FONT_SIZE
    );

    applyMainTheme(DEFAULT_THEME);
    applyNavbarTheme(DEFAULT_NAVBAR);
    applySidebarTheme(DEFAULT_SIDEBAR);
    applyFont(DEFAULT_FONT);
    applyFontSize(DEFAULT_FONT_SIZE);

    dispatchThemeChange();
  };


  /* =========================================================
     THEME CHANGE EVENT
     ========================================================= */

  function dispatchThemeChange() {

    document.dispatchEvent(
      new CustomEvent(
        "eventra:themechange",
        {
          detail: {
            theme: getPreference(
              THEME_KEY,
              DEFAULT_THEME
            ),

            navbar: getPreference(
              NAVBAR_KEY,
              DEFAULT_NAVBAR
            ),

            sidebar: getPreference(
              SIDEBAR_KEY,
              DEFAULT_SIDEBAR
            ),

            font: getPreference(
              FONT_KEY,
              DEFAULT_FONT
            ),

            fontSize: getPreference(
              FONT_SIZE_KEY,
              DEFAULT_FONT_SIZE
            )
          }
        }
      )
    );
  }


  /* =========================================================
     APPLY SAVED SETTINGS
     ========================================================= */

  function applySavedPreferences() {

    var theme = getPreference(
      THEME_KEY,
      DEFAULT_THEME
    );

    var navbar = getPreference(
      NAVBAR_KEY,
      DEFAULT_NAVBAR
    );

    var sidebar = getPreference(
      SIDEBAR_KEY,
      DEFAULT_SIDEBAR
    );

    var font = getPreference(
      FONT_KEY,
      DEFAULT_FONT
    );

    var fontSize = getPreference(
      FONT_SIZE_KEY,
      DEFAULT_FONT_SIZE
    );


    applyMainTheme(theme);
    applyNavbarTheme(navbar);
    applySidebarTheme(sidebar);
    applyFont(font);
    applyFontSize(fontSize);
  }


  /* =========================================================
     SYSTEM THEME LISTENER
     ========================================================= */

  if (window.matchMedia) {

    var mediaQuery =
      window.matchMedia(
        "(prefers-color-scheme: dark)"
      );

    mediaQuery.addEventListener(
      "change",
      function () {

        if (
          getPreference(
            THEME_KEY,
            DEFAULT_THEME
          ) === "system"
        ) {

          applyMainTheme("system");

          dispatchThemeChange();
        }

      }
    );
  }


  /* =========================================================
     INITIALIZE
     ========================================================= */

  document.addEventListener(
    "DOMContentLoaded",
    function () {

      applySavedPreferences();

    }
  );

})();