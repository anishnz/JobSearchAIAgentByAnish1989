/* kb_ask.js - the "Ask" page. Needs kb_common.js. Element ids match kb/templates/kb/ask.html. From CyberQuest. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  var root = document.getElementById("kb-app");
  var form = document.getElementById("kb-ask-form");
  var input = document.getElementById("kb-question");
  var btn = document.getElementById("kb-ask-btn");
  var busy = document.getElementById("kb-busy");
  var out = document.getElementById("kb-result");
  if (!root || !form || !input || !btn || !busy || !out || !window.KB) { return; }

  var el = window.KB.el;
  var askUrl = root.dataset.askUrl;
  var csrf = root.dataset.csrf;

  function setBusy(on) {
    btn.disabled = on;
    input.readOnly = on;
    busy.hidden = !on;
  }

  function showAnswer(data) {
    out.replaceChildren();
    var card = el("div", "card");
    card.appendChild(el("h2", null, "Answer"));
    var answer = el("div", null, data.answer || "No answer was returned.");
    answer.style.whiteSpace = "pre-wrap";
    card.appendChild(answer);
    out.appendChild(card);

    var sources = Array.isArray(data.sources) ? data.sources : [];
    var sCard = el("div", "card");
    sCard.appendChild(el("h3", null, "Sources"));
    if (!sources.length) {
      sCard.appendChild(el("p", "small muted", "No sources were used for this answer."));
    } else {
      var list = el("ul", "small");
      sources.forEach(function (s) {
        var li = el("li");
        li.appendChild(el("strong", null, "[" + s.n + "] " + (s.title || "Untitled") + (s.shared ? " (shared)" : "")));
        if (s.snippet) { li.appendChild(el("div", "muted", s.snippet + "...")); }
        list.appendChild(li);
      });
      sCard.appendChild(list);
    }
    out.appendChild(sCard);
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (btn.disabled) { return; }
    var question = input.value.trim();
    if (!question) {
      window.KB.showAlert(out, "error", "Please type a question first.");
      input.focus();
      return;
    }
    setBusy(true);
    out.replaceChildren();
    try {
      var data = await window.KB.call(askUrl, csrf, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question })
      });
      showAnswer(data);
    } catch (err) {
      window.KB.showAlert(out, "error", err.message);
    } finally {
      setBusy(false);
    }
  });

  // Ctrl + Enter also sends the question.
  input.addEventListener("keydown", function (e) {
    if (e.ctrlKey && e.key === "Enter") {
      e.preventDefault();
      form.requestSubmit();
    }
  });
});
