/* =========================================================
   EVENTRA - Ticket Check-in Scanner
   Uses the html5-qrcode library (loaded via CDN in scanner.html)
   to read a ticket's QR code from the device camera, then POSTs
   the raw token to the check-in/check-out endpoint for this event.
   The server re-verifies the signature — this file never decides
   whether a ticket is valid, it just relays what the camera saw.
   ========================================================= */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var config = window.EVENTRA_SCANNER;
    if (!config) {
      return;
    }

    var mode = "checkin";
    var resultPanel = document.getElementById("scan-result");
    var csrfInput = document.querySelector("#scan-csrf-form [name=csrfmiddlewaretoken]");
    var cameraSelect = document.getElementById("camera-select");
    var startBtn = document.getElementById("start-scanner-btn");
    var stopBtn = document.getElementById("stop-scanner-btn");
    var scanNextBtn = document.getElementById("scan-next-btn");
    var recentScansEl = document.getElementById("recent-scans");

    var lastCode = null;
    var lastScanTime = 0;
    var RESCAN_COOLDOWN_MS = 4000;
    var busy = false;
    var paused = false; // true right after a successful/duplicate/invalid result, until "Scan Next"
    var scanner = null;
    var recentScans = [];

    document.querySelectorAll("[data-scan-mode]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        mode = btn.getAttribute("data-scan-mode");
        document.querySelectorAll("[data-scan-mode]").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
      });
    });

    function showResult(resultType, message) {
      var suffix = resultType ? " result-" + resultType : "";
      resultPanel.className =
        "glass-card scan-result-panel p-3 mt-3 d-flex align-items-center justify-content-center text-center" +
        suffix;
      var p = document.createElement("p");
      p.className = "mb-0";
      p.textContent = message;
      resultPanel.innerHTML = "";
      resultPanel.appendChild(p);
    }

    function pushRecentScan(resultType, message) {
      recentScans.unshift({ type: resultType, message: message, time: new Date().toLocaleTimeString() });
      recentScans = recentScans.slice(0, 10);
      renderRecentScans();
    }

    function renderRecentScans() {
      if (!recentScansEl) return;
      if (!recentScans.length) {
        recentScansEl.innerHTML = '<p class="text-muted-custom small mb-0">No scans yet this session.</p>';
        return;
      }
      recentScansEl.innerHTML = "";
      recentScans.forEach(function (scan) {
        var badgeClass =
          scan.type === "success" ? "success" : scan.type === "duplicate" ? "warning" : "danger";
        var row = document.createElement("div");
        row.className = "d-flex justify-content-between align-items-start gap-2 pb-2";
        row.style.borderBottom = "1px solid rgba(255,255,255,0.08)";
        row.innerHTML =
          '<span class="badge-soft ' + badgeClass + '">' + scan.type + "</span>" +
          '<span class="small text-muted-custom flex-grow-1 mx-2">' + scan.message + "</span>" +
          '<span class="small text-muted-custom">' + scan.time + "</span>";
        recentScansEl.appendChild(row);
      });
    }

    function submitScan(token) {
      if (busy) {
        return;
      }
      busy = true;

      var url = mode === "checkin" ? config.checkInUrl : config.checkOutUrl;
      var body = new URLSearchParams();
      body.append("token", token);

      fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfInput ? csrfInput.value : "",
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: body.toString()
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          var resultType = data.success
            ? "success"
            : data.result === "duplicate"
            ? "duplicate"
            : "invalid";
          var message = data.message || "Scan processed.";
          showResult(resultType, message);
          pushRecentScan(resultType, message);

          // Pause continuous scanning after any definitive result so
          // staff can read it, then explicitly move on — matches the
          // spec's "Success/error feedback" + "Scan Next" workflow.
          paused = true;
          if (scanNextBtn) scanNextBtn.disabled = false;
        })
        .catch(function () {
          var message = "Couldn't reach the server. Check your connection and try again.";
          showResult("invalid", message);
          pushRecentScan("invalid", message);
        })
        .finally(function () {
          window.setTimeout(function () {
            busy = false;
          }, 800);
        });
    }

    function onScanSuccess(decodedText) {
      if (paused) {
        return;
      }
      var now = Date.now();
      if (decodedText === lastCode && now - lastScanTime < RESCAN_COOLDOWN_MS) {
        return; // ignore immediate re-reads of the same code by the camera
      }
      lastCode = decodedText;
      lastScanTime = now;
      submitScan(decodedText);
    }

    if (scanNextBtn) {
      scanNextBtn.addEventListener("click", function () {
        paused = false;
        lastCode = null;
        scanNextBtn.disabled = true;
        showResult("", "Ready for the next scan…");
      });
    }

    if (typeof Html5Qrcode === "undefined") {
      showResult("invalid", "Camera scanner library failed to load. Check your connection.");
      return;
    }

    scanner = new Html5Qrcode("qr-reader");

    function populateCameras() {
      return Html5Qrcode.getCameras().then(function (devices) {
        if (!devices || !devices.length) {
          showResult("invalid", "No camera found on this device.");
          return [];
        }
        cameraSelect.innerHTML = "";
        devices.forEach(function (device, idx) {
          var opt = document.createElement("option");
          opt.value = device.id;
          opt.textContent = device.label || "Camera " + (idx + 1);
          cameraSelect.appendChild(opt);
        });
        // Prefer the last camera in the list — on phones this is usually
        // the rear-facing one, what staff will use at the door.
        cameraSelect.selectedIndex = devices.length - 1;
        return devices;
      });
    }

    function startScanner() {
      var cameraId = cameraSelect.value;
      if (!cameraId) return;
      scanner
        .start(cameraId, { fps: 10, qrbox: 240 }, onScanSuccess)
        .then(function () {
          startBtn.disabled = true;
          stopBtn.disabled = false;
          cameraSelect.disabled = true;
        })
        .catch(function () {
          showResult("invalid", "Couldn't access the camera. Check permissions and try again.");
        });
    }

    function stopScanner() {
      scanner
        .stop()
        .then(function () {
          startBtn.disabled = false;
          stopBtn.disabled = true;
          scanNextBtn.disabled = true;
          cameraSelect.disabled = false;
          showResult("", "Scanner stopped.");
        })
        .catch(function () {
          /* already stopped */
        });
    }

    startBtn.addEventListener("click", startScanner);
    stopBtn.addEventListener("click", stopScanner);
    cameraSelect.addEventListener("change", function () {
      if (!stopBtn.disabled) {
        scanner.stop().then(startScanner);
      }
    });

    populateCameras()
      .then(function (devices) {
        if (devices && devices.length) {
          startScanner();
        }
      })
      .catch(function () {
        showResult("invalid", "Couldn't access the camera. Check permissions and try again.");
      });
  });
})();
