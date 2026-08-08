/* The judgement queue: ambient list, full-screen decision, numbered answers.
 *
 * Availability is the human's manual toggle (localStorage), sent to the
 * server so inadmissible requests never reach the wire. Every rendered queue
 * carries the deck sha it was derived from; an answer threads that sha back
 * and the service stamps it as approved_sha — the audit of what was read.
 * Card content renders as textContent only, never HTML: evidence is
 * agent-authored and agents do not get script into the approval surface. */
"use strict";

const state = { sha: null, open: null };

function level() {
  return localStorage.getItem("availability") || "open";
}

function setLevel(value) {
  localStorage.setItem("availability", value);
  document.querySelectorAll("#availability button").forEach((b) =>
    b.classList.toggle("active", b.dataset.level === value));
  refresh();
}

async function refresh() {
  const res = await fetch(`/judge/api/queue?availability=${level()}`);
  if (!res.ok) { alanPwaToast(`queue: ${res.status}`, true); return; }
  const data = await res.json();
  state.sha = data.sha;
  render(data.requests);
}

function render(requests) {
  const main = document.getElementById("queue");
  main.replaceChildren();
  if (!requests.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = level() === "silent" ? "silent — queue withheld" : "nothing awaits you";
    main.appendChild(empty);
    return;
  }
  for (const req of requests) main.appendChild(card(req));
  if (state.open) {
    const still = main.querySelector(`[data-id="${CSS.escape(state.open)}"]`);
    if (still) still.classList.add("open");
  }
}

function card(req) {
  const article = document.createElement("article");
  article.dataset.id = req.id;

  const head = document.createElement("header");
  const title = document.createElement("h2");
  title.textContent = req.title;
  const summary = document.createElement("p");
  summary.textContent = req.summary;
  const meta = document.createElement("p");
  meta.className = "meta";
  const hours = (Date.now() - Date.parse(req.asked)) / 3600000;
  const age = hours < 2 ? "fresh" : hours < 48 ? `asked ${Math.round(hours)}h ago` : `asked ${Math.round(hours / 24)}d ago — evidence may be stale`;
  meta.textContent = `${req.producer} · ${age}${req.expires ? " · expires " + req.expires.slice(11, 16) : ""}`;
  if (hours >= 48) meta.classList.add("stale");
  head.append(title, summary, meta);
  head.onclick = () => {
    state.open = article.classList.contains("open") ? null : req.id;
    document.querySelectorAll("article.open").forEach((a) => a.classList.remove("open"));
    if (state.open) article.classList.add("open");
  };

  const detail = document.createElement("div");
  detail.className = "detail";
  if (req.body.trim()) {
    const body = document.createElement("pre");
    body.textContent = req.body;
    detail.appendChild(body);
  }

  const answers = document.createElement("div");
  answers.className = "answers";
  req.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.textContent = `${index + 1}. ${option}`;
    button.onclick = () => answer(req.id, option);
    answers.appendChild(button);
  });
  const free = document.createElement("form");
  const input = document.createElement("input");
  input.placeholder = req.options.length ? "or answer in your own words" : "answer";
  input.enterKeyHint = "send";
  free.appendChild(input);
  free.onsubmit = (event) => {
    event.preventDefault();
    if (input.value.trim()) answer(req.id, input.value.trim());
  };
  answers.appendChild(free);
  detail.appendChild(answers);

  article.append(head, detail);
  return article;
}

async function answer(id, value) {
  const res = await fetch("/judge/api/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, answer: value, sha: state.sha, surface: "pwa" }),
  });
  if (res.ok) {
    alanPwaToast(`answered: ${value}`);
    state.open = null;
  } else {
    alanPwaToast(`${res.status}: ${await res.text()}`, true);
  }
  refresh();
}

document.querySelectorAll("#availability button").forEach((b) => {
  b.onclick = () => setLevel(b.dataset.level);
});
setLevel(level());
setInterval(refresh, 60000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/judge/sw.js");
