(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var config = window.EVENTRA_CHATBOT;
    if (!config) return;

    var toggleBtn = document.getElementById("chatbot-toggle-btn");
    var panel = document.getElementById("chatbot-panel");
    var closeBtn = document.getElementById("chatbot-close-btn");
    var clearBtn = document.getElementById("chatbot-clear-btn");
    var messagesEl = document.getElementById("chatbot-messages");
    var errorEl = document.getElementById("chatbot-error");
    var form = document.getElementById("chatbot-form");
    var input = document.getElementById("chatbot-input");
    var sendBtn = document.getElementById("chatbot-send-btn");
    var suggestionsEl = document.getElementById("chatbot-suggestions");

    var WELCOME = "Hi! I'm the Eventra Assistant. Ask me about events, your registrations, tickets, or certificates.";
    var opened = false;

    function getCookie(name) {
      var value = "; " + document.cookie;
      var parts = value.split("; " + name + "=");
      if (parts.length === 2) return parts.pop().split(";").shift();
      return "";
    }

    function scrollToBottom() {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function appendMessage(role, text) {
      var div = document.createElement("div");
      div.className = "chatbot-msg " + role;
      div.textContent = text;
      messagesEl.appendChild(div);
      scrollToBottom();
    }

    function showTyping() {
      var div = document.createElement("div");
      div.className = "chatbot-typing";
      div.id = "chatbot-typing-indicator";
      div.innerHTML = "<span></span><span></span><span></span>";
      messagesEl.appendChild(div);
      scrollToBottom();
    }

    function hideTyping() {
      var el = document.getElementById("chatbot-typing-indicator");
      if (el) el.remove();
    }

    function showError(message) {
      errorEl.textContent = message;
      errorEl.classList.remove("d-none");
    }

    function clearError() {
      errorEl.classList.add("d-none");
      errorEl.textContent = "";
    }

    function resetConversation() {
      messagesEl.innerHTML = "";
      appendMessage("assistant", WELCOME);
      clearError();
    }

    function openPanel() {
      panel.classList.remove("d-none");
      opened = true;
      if (!messagesEl.children.length) {
        resetConversation();
      }
      input.focus();
    }

    function closePanel() {
      panel.classList.add("d-none");
    }

    toggleBtn.addEventListener("click", function () {
      if (panel.classList.contains("d-none")) {
        openPanel();
      } else {
        closePanel();
      }
    });
    closeBtn.addEventListener("click", closePanel);
    clearBtn.addEventListener("click", resetConversation);

    if (suggestionsEl) {
      suggestionsEl.addEventListener("click", function (e) {
        var chip = e.target.closest("[data-question]");
        if (!chip) return;
        input.value = chip.getAttribute("data-question");
        form.dispatchEvent(new Event("submit", { cancelable: true }));
      });
    }

    function sendMessage(text) {
      appendMessage("user", text);
      clearError();
      showTyping();
      sendBtn.disabled = true;

      fetch(config.sendUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCookie("csrftoken"),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ message: text }).toString(),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (result) {
          hideTyping();
          if (result.ok && result.data.success) {
            appendMessage("assistant", result.data.reply);
          } else {
            showError((result.data && result.data.error) || "Something went wrong. Please try again.");
          }
        })
        .catch(function () {
          hideTyping();
          showError("Couldn't reach the server. Check your connection and try again.");
        })
        .finally(function () {
          sendBtn.disabled = false;
        });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      sendMessage(text);
    });
  });
})();
