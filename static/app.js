// ParseAnything web page
// Sends each uploaded file to /parse on this same server, then shows its result card.

const ACCEPTED = ["pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx", "txt", "md", "markdown", "html", "htm", "rtf", "eml", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "heic"];
const STATUS_LABELS = { success: "Complete", partial: "Needs review", error: "Failed" };
const FORMAT_LABELS = { scanned_pdf: "Scanned PDF", unscanned_pdf: "Unscanned PDF" };

let queue = [];   // files waiting to be parsed
let busy = false; // true while parsing

const $ = (id) => document.getElementById(id);

// ===== Mobile menu =====
$("menuToggle").addEventListener("click", () => $("navLinks").classList.toggle("open"));
$("navLinks").querySelectorAll("a").forEach((a) =>
  a.addEventListener("click", () => $("navLinks").classList.remove("open"))
);

// ===== Scroll animations =====
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        observer.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.15 }
);
document.querySelectorAll(".fade-in").forEach((el) => observer.observe(el));

// ===== Picking files =====
const dropZone = $("dropZone");
const fileInput = $("fileInput");

$("chooseBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  addFiles(fileInput.files);
  fileInput.value = "";
});

["dragenter", "dragover"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
  })
);
dropZone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

function addFiles(fileList) {
  const rejected = [];
  Array.from(fileList).forEach((file) => {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (ACCEPTED.includes(ext)) {
      queue.push(file);
    } else {
      rejected.push(file.name);
    }
  });

  if (rejected.length) {
    setStatus(`Skipped ${rejected.length} file(s) with a type that is not supported: ${rejected.join(", ")}`, "error");
  } else {
    setStatus("");
  }
  renderQueue();
}

function renderQueue() {
  const box = $("queueBox");
  const list = $("queueList");
  list.innerHTML = "";
  box.hidden = queue.length === 0;
  $("queueTitle").textContent = `${queue.length} file${queue.length === 1 ? "" : "s"} ready to parse`;

  queue.forEach((file, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${esc(file.name)}</span>
      <span class="muted">${formatSize(file.size)}
      <button class="remove" type="button" data-index="${i}" aria-label="Remove file">&times;</button></span>`;
    list.appendChild(li);
  });

  list.querySelectorAll(".remove").forEach((btn) =>
    btn.addEventListener("click", () => {
      queue.splice(Number(btn.dataset.index), 1);
      renderQueue();
    })
  );
  $("parseBtn").disabled = busy || queue.length === 0;
}

$("clearBtn").addEventListener("click", () => {
  if (busy) return;
  queue = [];
  $("batch").innerHTML = "";
  setStatus("");
  renderQueue();
});

// ===== Parsing every file, one at a time =====
$("parseBtn").addEventListener("click", parseAll);

async function parseAll() {
  if (busy || queue.length === 0) return;
  busy = true;
  $("parseBtn").disabled = true;
  $("parseBtn").textContent = "Parsing...";

  const files = queue.slice();
  const save = $("saveToggle").checked;
  const batch = $("batch");
  batch.innerHTML = "";

  let failed = 0;
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    setStatus(`Parsing ${i + 1} of ${files.length}: ${file.name}. Scanned pages can take a little longer.`);
    const card = createCard(file, "working");
    batch.appendChild(card);

    const outcome = await parseOne(file, save);
    if (outcome.ok) {
      fillCard(card, outcome.data);
    } else {
      failed++;
      fillCardError(card, file, outcome.message);
    }
  }

  const done = files.length - failed;
  setStatus(
    failed
      ? `Finished. ${done} of ${files.length} files parsed. ${failed} failed. See the cards below.`
      : `Finished! All ${files.length} file${files.length === 1 ? "" : "s"} parsed. Your results are below.`,
    failed ? "error" : "success"
  );

  queue = [];
  busy = false;
  $("parseBtn").textContent = "Parse all files";
  renderQueue();
  batch.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function parseOne(file, save) {
  const form = new FormData();
  form.append("file", file);

  let response;
  try {
    response = await fetch(`/parse?save=${save}`, { method: "POST", body: form });
  } catch (err) {
    return { ok: false, message: "Could not reach the server. Make sure ParseAnything is running." };
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    return { ok: false, message: errorMessage(body, response.status) };
  }
  return { ok: true, data: body };
}

function errorMessage(body, status) {
  const detail = body && body.detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  if (typeof detail === "string") return detail;
  return `Something went wrong on the server (code ${status}).`;
}

// ===== Result cards: one card per file =====
function createCard(file, state) {
  const card = document.createElement("article");
  card.className = "card file-card";
  const pillText = state === "working" ? "Parsing..." : "";
  card.innerHTML = `
    <div class="file-head">
      <div>
        <h3 class="file-name">${esc(file.name)}</h3>
        <p class="muted small">${formatSize(file.size)}</p>
      </div>
      <span class="pill working">${pillText}</span>
    </div>`;
  return card;
}

function fillCard(card, data) {
  const statusClass = data.status || "success";
  const head = card.querySelector(".file-head");
  head.querySelector(".pill").className = `pill ${statusClass}`;
  head.querySelector(".pill").textContent = STATUS_LABELS[data.status] || data.status;

  const fileTypeLabel = `Type: ${formatLabel(data.format)}`;
  head.querySelector("div").insertAdjacentHTML("beforeend", `<p class="muted small">${esc(fileTypeLabel)}</p>`);
  if (data.format === "scanned_pdf") {
    head.querySelector("div").insertAdjacentHTML("beforeend",
      `<p class="muted small">Text was read from images of the pages with OCR, so check it carefully.</p>`);
  }

  card.insertAdjacentHTML("beforeend", `
    <div class="mini-metrics">
      <div><strong>${data.pages}</strong><span>Pages</span></div>
      <div><strong>${data.blocks.length}</strong><span>Text and table pieces</span></div>
      <div><strong>${data.errors ? data.errors.length : 0}</strong><span>Things to check</span></div>
    </div>
    <div class="dash-toolbar">
      <div class="tabs">
        <button class="tab active" data-tab="readable" type="button">Readable view</button>
        <button class="tab" data-tab="blocks" type="button">Blocks</button>
        <button class="tab" data-tab="json" type="button">Raw JSON</button>
      </div>
      <div class="downloads">
        <button class="btn btn-outline btn-small" data-dl="md" type="button">Download Markdown</button>
        <button class="btn btn-outline btn-small" data-dl="json" type="button">Download JSON</button>
      </div>
    </div>
    <div class="card panel" data-panel="readable"><div class="readable">${renderReadable(data.blocks)}</div></div>
    <div class="card panel" data-panel="blocks" hidden>
      <div class="filter-row">
        <label>Show:
          <select data-filter>
            <option value="all">All pieces</option>
            <option value="review">Only pieces that need a check</option>
          </select>
        </label>
      </div>
      <div data-blocks></div>
    </div>
    <div class="card panel" data-panel="json" hidden><pre class="preview">${esc(JSON.stringify(data, null, 2))}</pre></div>
  `);

  if (data.errors && data.errors.length) {
    const list = data.errors.map((e) => `<li>${esc(e.message || e.code)}${e.page ? ` (page ${e.page})` : ""}</li>`).join("");
    card.insertAdjacentHTML("beforeend", `<div class="card errors"><h4>Things to check</h4><ul>${list}</ul></div>`);
  }

  wireCard(card, data);
}

function fillCardError(card, file, message) {
  const pill = card.querySelector(".pill");
  pill.className = "pill error";
  pill.textContent = "Failed";
  card.insertAdjacentHTML("beforeend", `<p class="error-text">${esc(message)}</p>`);
}

function wireCard(card, data) {
  // Tabs inside this card only
  card.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      card.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === btn));
      card.querySelectorAll("[data-panel]").forEach((p) => {
        p.hidden = p.dataset.panel !== btn.dataset.tab;
      });
    })
  );

  // Block list with the filter
  const blockBox = card.querySelector("[data-blocks]");
  const filter = card.querySelector("[data-filter]");
  const drawBlocks = () => {
    blockBox.innerHTML = renderBlocks(data.blocks, filter.value);
  };
  filter.addEventListener("change", drawBlocks);
  drawBlocks();

  // Downloads
  const stem = data.filename.replace(/\.[^.]+$/, "");
  card.querySelector('[data-dl="md"]').addEventListener("click", () =>
    download(`${stem}.md`, data.markdown || "", "text/markdown")
  );
  card.querySelector('[data-dl="json"]').addEventListener("click", () =>
    download(`${stem}.json`, JSON.stringify(data, null, 2), "application/json")
  );
}

// Readable view: rebuilt from blocks, so tables, sheets and figures all show
function renderReadable(blocks) {
  let html = "";
  let lastPage = null;

  blocks.forEach((b) => {
    if (b.type === "header" || b.type === "footer") return; // shown in the Blocks tab only
    if (b.type !== "spreadsheet" && b.page !== lastPage) {
      html += `<h3 class="page-head">Page ${b.page}</h3>`;
      lastPage = b.page;
    }

    if (b.type === "spreadsheet") {
      html += `<h3 class="page-head">Sheet: ${esc((b.metadata && b.metadata.sheet) || "Untitled")}</h3>`;
      html += tableHtml(b.metadata.rows);
    } else if (b.type === "table") {
      html += tableHtml(b.metadata.rows);
    } else if (b.type === "figure") {
      html += `<p class="figure-note">An image or chart was found here. Its contents are not read yet.</p>`;
    } else if (b.type === "heading") {
      html += `<h4>${esc(b.text)}</h4>`;
    } else if (b.type === "list") {
      html += `<p class="list-item">&bull; ${esc(b.text)}</p>`;
    } else if (b.type === "equation") {
      html += `<pre class="equation">${esc(b.text)}</pre>`;
    } else if (b.type === "caption") {
      html += `<p class="caption"><em>${esc(b.text)}</em></p>`;
    } else if (b.type === "footnote") {
      html += `<p class="footnote">${esc(b.text)}</p>`;
    } else if (b.type === "slide") {
      html += `<p class="slide-text">${esc(b.text)}</p>`;
    } else if (b.text) {
      html += `<p>${esc(b.text)}</p>`;
    }
  });

  return html || '<p class="muted">No readable text was found in this file.</p>';
}

function tableHtml(rows) {
  if (!rows || !rows.length) return "";
  const limit = 200;
  const shown = rows.slice(0, limit);
  const [head, ...body] = shown;
  let html = '<div class="table-wrap"><table><thead><tr>';
  html += (head || []).map((c) => `<th>${esc(c)}</th>`).join("");
  html += "</tr></thead><tbody>";
  body.forEach((row) => {
    html += "<tr>" + row.map((c) => `<td>${esc(c)}</td>`).join("") + "</tr>";
  });
  html += "</tbody></table></div>";
  if (rows.length > limit) {
    html += `<p class="muted small">Showing the first ${limit} of ${rows.length} rows.</p>`;
  }
  return html;
}

// Blocks: one card per piece, with its confidence score
function renderBlocks(blocks, filter) {
  const shown = blocks.filter((b) => filter === "all" || b.status !== "ok");
  if (!shown.length) return '<p class="muted">Nothing to show here.</p>';

  return shown.map((b) => {
    const pct = Math.round(b.confidence * 100);
    const tone = b.confidence >= 0.9 ? "high" : b.confidence >= 0.75 ? "mid" : "low";
    const body = b.metadata && Array.isArray(b.metadata.rows) && b.metadata.rows.length
      ? tableHtml(b.metadata.rows)
      : `<p class="block-text">${esc(b.text || "(no text)")}</p>`;
    return `
      <div class="block-card${b.status !== "ok" ? " flagged" : ""}">
        <div class="block-head">
          <span class="badge-type">${esc(b.type)}</span>
          <span>Page ${b.page}</span>
          <span class="muted small">${esc(b.id)}</span>
          <span class="conf ${tone}">Confidence ${pct}%</span>
        </div>
        ${body}
        ${b.status !== "ok" ? '<p class="flag">Flagged. Please double-check this part.</p>' : ""}
        <p class="muted small">Found by: ${esc(b.source || "unknown")}</p>
      </div>`;
  }).join("");
}

// ===== Downloads =====
function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ===== Helpers =====
function setStatus(message, type = "") {
  const el = $("statusMsg");
  el.textContent = message;
  el.className = "status " + type;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatLabel(format) {
  return FORMAT_LABELS[format] || String(format || "-").toUpperCase();
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
