/* kb_manage.js - the Knowledge Base documents page. Needs kb_common.js. From CyberQuest.
   Element ids match kb/templates/kb/manage.html. Endpoint URLs come from data-* attributes. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  var root = document.getElementById("kb-app");
  if (!root || !window.KB) { return; }

  var el = window.KB.el;
  var csrf = root.dataset.csrf;
  var documentsUrl = root.dataset.documentsUrl;
  var interviewUrl = root.dataset.interviewUrl;
  var isAdmin = root.dataset.isAdmin === "1";
  var alertBox = document.getElementById("kb-alert");
  var docsBody = document.getElementById("kb-docs-body");

  function flash(kind, message) { window.KB.showAlert(alertBox, kind, message); }

  // ---- document list ----
  function messageRow(text, cls) {
    var tr = el("tr");
    var td = el("td", cls, text);
    td.colSpan = 5;
    tr.appendChild(td);
    return tr;
  }

  function renderDocs(docs) {
    docsBody.replaceChildren();
    if (!docs.length) {
      docsBody.appendChild(messageRow("No documents yet. Upload one above.", "muted"));
      return;
    }
    docs.forEach(function (d) {
      var tr = el("tr");
      tr.appendChild(el("td", null, d.title));
      tr.appendChild(el("td", "muted", d.tags || ""));
      var who = el("td");
      who.appendChild(el("span", d.shared ? "badge blue" : "badge", d.shared ? "Everyone (shared)" : "Private"));
      tr.appendChild(who);
      var chunks = el("td", null, String(d.chunks));
      chunks.style.textAlign = "right";
      tr.appendChild(chunks);
      var act = el("td");
      act.style.textAlign = "right";
      if (!d.shared || isAdmin) {
        var del = el("button", "light", "Delete");
        del.type = "button";
        del.setAttribute("aria-label", "Delete " + d.title);
        del.addEventListener("click", function () { removeDoc(d); });
        act.appendChild(del);
      }
      tr.appendChild(act);
      docsBody.appendChild(tr);
    });
  }

  async function loadDocs() {
    try {
      var data = await window.KB.call(documentsUrl, csrf);
      renderDocs(Array.isArray(data.documents) ? data.documents : []);
    } catch (err) {
      docsBody.replaceChildren();
      docsBody.appendChild(messageRow(err.message, "muted"));
    }
  }

  async function removeDoc(d) {
    var where = d.shared ? " from the SHARED knowledge base (all users)" : "";
    if (!window.confirm("Delete \"" + d.title + "\"" + where + "? This cannot be undone.")) { return; }
    try {
      await window.KB.call(documentsUrl + encodeURIComponent(d.doc_id) + "/", csrf, { method: "DELETE" });
      flash("info", "Deleted \"" + d.title + "\".");
      await loadDocs();
    } catch (err) {
      flash("error", err.message);
    }
  }

  // ---- upload ----
  var upForm = document.getElementById("kb-upload-form");
  var upBtn = document.getElementById("kb-upload-btn");
  var upBusy = document.getElementById("kb-upload-busy");
  var fileInput = document.getElementById("kb-file");
  var sharedBox = document.getElementById("kb-shared");

  upForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (upBtn.disabled) { return; }
    var file = fileInput.files[0];
    if (!file) {
      flash("error", "Please choose a file to upload.");
      return;
    }
    var fd = new FormData();
    fd.append("file", file);
    fd.append("title", document.getElementById("kb-title").value.trim());
    fd.append("tags", document.getElementById("kb-tags").value.trim());
    fd.append("shared", sharedBox && sharedBox.checked ? "1" : "0");
    upBtn.disabled = true;
    upBusy.hidden = false;
    try {
      // No Content-Type header: the browser adds the multipart boundary itself.
      var data = await window.KB.call(documentsUrl, csrf, { method: "POST", body: fd });
      flash("success", "Uploaded. The document was split into " + data.chunks + " chunks.");
      upForm.reset();
      await loadDocs();
    } catch (err) {
      flash("error", err.message);
    } finally {
      upBtn.disabled = false;
      upBusy.hidden = true;
    }
  });

  // ---- interview practice ----
  var intForm = document.getElementById("kb-int-form");
  var intBtn = document.getElementById("kb-int-btn");
  var intBusy = document.getElementById("kb-int-busy");
  var intOut = document.getElementById("kb-int-out");

  function showQuestions(data) {
    intOut.replaceChildren();
    if (!data.parsed) {
      intOut.appendChild(el("div", "msg warning",
        "The AI did not return the questions in the expected format. Here is its raw answer; try again for a cleaner result."));
      intOut.appendChild(el("pre", null, data.raw || ""));
      return;
    }
    var questions = Array.isArray(data.questions) ? data.questions : [];
    if (!questions.length) {
      intOut.appendChild(el("div", "msg warning", "No questions were returned. Try a different job or topic."));
    }
    questions.forEach(function (q, i) {
      var box = el("div", "card");
      box.appendChild(el("h3", null, "Q" + (i + 1) + ". " + (q.question || "")));
      var det = el("details");
      det.appendChild(el("summary", "small", "Show answer tip"));
      det.appendChild(el("p", "small", q.tip || ""));
      box.appendChild(det);
      intOut.appendChild(box);
    });
    var titles = [];
    (Array.isArray(data.sources) ? data.sources : []).forEach(function (s) {
      if (titles.indexOf(s.title) === -1) { titles.push(s.title); }
    });
    if (titles.length) { intOut.appendChild(el("p", "small muted", "Based on: " + titles.join(", "))); }
  }

  intForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (intBtn.disabled) { return; }
    var topic = document.getElementById("kb-topic").value.trim();
    intOut.replaceChildren();
    if (!topic) {
      window.KB.showAlert(intOut, "error", "Please type a job or topic first.");
      return;
    }
    var count = parseInt(document.getElementById("kb-count").value, 10);
    if (!(count >= 1 && count <= 15)) {
      window.KB.showAlert(intOut, "error", "The number of questions must be a whole number from 1 to 15.");
      return;
    }
    intBtn.disabled = true;
    intBusy.hidden = false;
    try {
      var data = await window.KB.call(interviewUrl, csrf, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: topic, count: count })
      });
      showQuestions(data);
    } catch (err) {
      window.KB.showAlert(intOut, "error", err.message);
    } finally {
      intBtn.disabled = false;
      intBusy.hidden = true;
    }
  });

  // ---- AI model settings (admin only: the section is not in the page for other users) ----
  var modelUrl = root.dataset.modelUrl;
  var modelTestUrl = root.dataset.modelTestUrl;
  var modelForm = document.getElementById("kb-model-form");
  if (modelUrl && modelTestUrl && modelForm) {
    var mAlert = document.getElementById("kb-model-alert");
    var mBusy = document.getElementById("kb-model-busy");
    var mSave = document.getElementById("kb-model-save");
    var mTest = document.getElementById("kb-model-test");
    var fields = {
      display_name: document.getElementById("kb-m-name"),
      base_url: document.getElementById("kb-m-url"),
      model_id: document.getElementById("kb-m-id"),
      temperature: document.getElementById("kb-m-temp"),
      max_tokens: document.getElementById("kb-m-tokens"),
      timeout: document.getElementById("kb-m-timeout")
    };
    var keyInput = document.getElementById("kb-m-key");
    var keyMask = document.getElementById("kb-m-key-mask");

    function fillModel(cfg) {
      Object.keys(fields).forEach(function (k) {
        fields[k].value = cfg[k] === undefined || cfg[k] === null ? "" : String(cfg[k]);
      });
      keyMask.textContent = cfg.api_key_masked || "not set";
      keyInput.value = "";
    }

    function setModelBusy(on) {
      mSave.disabled = on;
      mTest.disabled = on;
      mBusy.hidden = !on;
    }

    async function loadModel() {
      try {
        fillModel(await window.KB.call(modelUrl, csrf));
      } catch (err) {
        window.KB.showAlert(mAlert, "error", "Could not load the model settings. " + err.message);
      }
    }

    modelForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (mSave.disabled) { return; }
      var payload = {};
      Object.keys(fields).forEach(function (k) { payload[k] = fields[k].value.trim(); });
      payload.api_key = keyInput.value.trim();
      setModelBusy(true);
      try {
        var cfg = await window.KB.call(modelUrl, csrf, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        fillModel(cfg);
        window.KB.showAlert(mAlert, "success", "Model settings saved.");
      } catch (err) {
        window.KB.showAlert(mAlert, "error", err.message);
      } finally {
        setModelBusy(false);
      }
    });

    mTest.addEventListener("click", async function () {
      if (mTest.disabled) { return; }
      setModelBusy(true);
      try {
        var res = await window.KB.call(modelTestUrl, csrf, { method: "POST" });
        window.KB.showAlert(mAlert, "success", "Connection works. The model replied: " + (res.reply || "(empty reply)"));
      } catch (err) {
        window.KB.showAlert(mAlert, "error", "Connection test failed. " + err.message);
      } finally {
        setModelBusy(false);
      }
    });

    loadModel();
  }

  loadDocs();
});
