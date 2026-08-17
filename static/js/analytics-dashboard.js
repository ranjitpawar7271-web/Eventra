/* =========================================================
   EVENTRA - Analytics Dashboard
   Reads the {labels, data} payloads embedded via json_script
   in analytics_dashboard.html and renders them with Chart.js.

   Series colors (primary/secondary/accent/success/danger) stay
   fixed hex values, same as any qualitative data-viz palette.
   Chart CHROME (axis labels, legend text, gridlines) is derived
   from the active theme so it stays readable in both Light and
   Dark, and updates live if the user flips the switcher.
   ========================================================= */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var dataEl = document.getElementById("analytics-chart-data");
    if (!dataEl || typeof Chart === "undefined") {
      return;
    }
    var charts = JSON.parse(dataEl.textContent);
    var chartInstances = [];

    var SERIES = {
      primary: "#2563EB",
      secondary: "#38BDF8",
      accent: "#F59E0B",
      success: "#10B981",
      danger: "#EF4444"
    };

    function chromeColors() {
      var isDark = document.documentElement.getAttribute("data-theme") === "dark";
      return isDark
        ? { text: "#F5F5F7", muted: "#A1A1A6", grid: "rgba(255, 255, 255, 0.08)" }
        : { text: "#111111", muted: "#6B6B6F", grid: "rgba(0, 0, 0, 0.08)" };
    }

    function applyChrome() {
      var chrome = chromeColors();
      Chart.defaults.color = chrome.muted;
      Chart.defaults.borderColor = chrome.grid;
      Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
      chartInstances.forEach(function (chart) {
        if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
          chart.options.plugins.legend.labels.color = chrome.text;
        }
        ["x", "y"].forEach(function (axis) {
          if (chart.options.scales && chart.options.scales[axis]) {
            chart.options.scales[axis].ticks.color = chrome.muted;
            chart.options.scales[axis].grid.color = chrome.grid;
          }
        });
        chart.update("none");
      });
    }

    function baseOptions(extra) {
      var chrome = chromeColors();
      var opts = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: chrome.text } }
        },
        scales: {
          x: { ticks: { color: chrome.muted }, grid: { color: chrome.grid } },
          y: { ticks: { color: chrome.muted }, grid: { color: chrome.grid }, beginAtZero: true }
        }
      };
      return Object.assign(opts, extra || {});
    }

    function track(chart) {
      chartInstances.push(chart);
      return chart;
    }

    function lineChart(canvasId, payload, label, color) {
      var el = document.getElementById(canvasId);
      if (!el) return;
      track(new Chart(el, {
        type: "line",
        data: {
          labels: payload.labels,
          datasets: [{
            label: label,
            data: payload.data,
            borderColor: color,
            backgroundColor: color + "33",
            fill: true,
            tension: 0.35,
            pointRadius: 3
          }]
        },
        options: baseOptions({ plugins: { legend: { display: false } } })
      }));
    }

    function barChart(canvasId, payload, label, color, horizontal) {
      var el = document.getElementById(canvasId);
      if (!el) return;
      track(new Chart(el, {
        type: "bar",
        data: {
          labels: payload.labels,
          datasets: [{
            label: label,
            data: payload.data,
            backgroundColor: color,
            borderRadius: 6,
            maxBarThickness: 36
          }]
        },
        options: baseOptions({
          indexAxis: horizontal ? "y" : "x",
          plugins: { legend: { display: false } }
        })
      }));
    }

    // 1. Registration trends
    lineChart("chart-registration-trends", charts.registration_trends, "Registrations", SERIES.primary);

    // 2. Attendance trends
    lineChart("chart-attendance-trends", charts.attendance_trends, "Checked In", SERIES.secondary);

    // 3. Revenue vs. expense trends
    var reEl = document.getElementById("chart-revenue-expense");
    if (reEl && charts.revenue_expense_trends) {
      var re = charts.revenue_expense_trends;
      track(new Chart(reEl, {
        type: "bar",
        data: {
          labels: re.labels,
          datasets: [
            { label: "Revenue", data: re.revenue, backgroundColor: SERIES.success, borderRadius: 6 },
            { label: "Expense", data: re.expense, backgroundColor: SERIES.danger, borderRadius: 6 }
          ]
        },
        options: baseOptions()
      }));
    }

    // 4. Event popularity
    barChart("chart-event-popularity", charts.event_popularity, "Registrations", SERIES.accent, true);

    // 5. Vendor ratings
    barChart("chart-vendor-ratings", charts.vendor_ratings, "Performance Score (/5)", SERIES.secondary, true);

    // 6. Resource usage
    barChart("chart-resource-usage", charts.resource_usage, "Units Allocated", SERIES.primary, true);

    // Keep chart chrome in sync if the user flips Light/Dark/System
    // without reloading (theme-switcher.js dispatches this event).
    document.addEventListener("eventra:themechange", applyChrome);
  });
})();
