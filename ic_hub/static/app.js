"use strict";
// Every server string reaches the page through textContent; no HTML is ever built from it.

const TOKEN = document.querySelector('meta[name="hub-token"]').content;
const $ = (id) => document.getElementById(id);
const REPLAY_MS = 250;
const POLL_MS = 200;

let currentRun = null;
let replayTimer = null;

async function api(method, path, body) {
  const options = { method, headers: { "X-Hub-Token": TOKEN } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  return { ok: response.ok, status: response.status, data };
}

function cell(row, text) {
  const td = document.createElement("td");
  td.textContent = text;
  row.appendChild(td);
  return td;
}

async function loadAlerts() {
  const { data } = await api("GET", "/api/alerts");
  const body = document.querySelector("#alerts tbody");
  body.replaceChildren();
  $("play-alert").replaceChildren();
  for (const a of data.alerts) {
    const row = document.createElement("tr");
    cell(row, a.alert_id);
    cell(row, a.service);
    cell(row, a.metric);
    cell(row, a.source);
    cell(row, a.summary);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Run";
    button.addEventListener("click", () => startRun(a.alert_id));
    cell(row, "").appendChild(button);
    body.appendChild(row);
    const option = document.createElement("option");
    option.value = a.alert_id;
    option.textContent = `${a.alert_id} (${a.service})`;
    $("play-alert").appendChild(option);
  }
}

function runRequest(alertId) {
  const request = { alert_id: alertId, mode: $("mode").value, fix_outcome: $("fix").value };
  const deadline = $("deadline").value;
  if (deadline !== "") request.deadline_s = Number(deadline);
  return request;
}

async function startRun(alertId) {
  $("run-error").textContent = "";
  clearReplay();
  const { ok, data } = await api("POST", "/api/runs", runRequest(alertId));
  if (!ok) {
    $("run-error").textContent = describe(data);
    return;
  }
  currentRun = data.run_id;
  $("run-status").textContent = `Running ${alertId}...`;
  pollRun(data.run_id);
}

function describe(data) {
  const fields = Object.entries(data.fields || {}).map(([k, v]) => `${k}: ${v}`);
  return [data.error, ...fields].join(" | ");
}

async function pollRun(runId) {
  const { ok, data } = await api("GET", `/api/runs/${runId}`);
  if (!ok || runId !== currentRun) return;
  showApproval(runId, data.pending);
  if (data.status === "running") {
    setTimeout(() => pollRun(runId), POLL_MS);
  } else if (data.status === "error") {
    $("run-status").textContent = `Run failed: ${data.error}`;
  } else {
    showResult(data.result);
  }
}

function showApproval(runId, pending) {
  const box = $("approval");
  box.hidden = pending === null;
  if (pending === null) return;
  $("approval-target").textContent = pending.target;
  $("approval-left").textContent = pending.remaining_s.toFixed(1);
  const answer = async (decision) => {
    const { data } = await api("POST", `/api/runs/${runId}/approval`, { nonce: pending.nonce, decision });
    if (data.outcome !== "accepted") $("run-error").textContent = `Answer not accepted: ${data.outcome}`;
  };
  $("approve").onclick = () => answer("approve");
  $("deny").onclick = () => answer("deny");
}

function clearReplay() {
  clearTimeout(replayTimer);
  $("trace").replaceChildren();
  $("decisions").textContent = "";
  $("skip").hidden = true;
  setPostmortem(null);
}

function eventText(e) {
  const fields = Object.entries(e.fields).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : v}`);
  return `[t+${e.elapsed_s.toFixed(2)}s] ${e.kind} ${fields.join(" ")}`;
}

function showResult(result) {
  $("run-status").textContent = `Replaying the finished trace. Final state: ${result.state}`;
  const list = $("trace");
  let i = 0;
  const finish = () => {
    clearTimeout(replayTimer);
    for (; i < result.trace.length; i++) appendEvent(list, result.trace[i]);
    $("skip").hidden = true;
    $("decisions").textContent = result.decision_lines.join("\n");
    setPostmortem(result);
    $("run-status").textContent = `Finished. Final state: ${result.state}`;
  };
  $("skip").hidden = false;
  $("skip").onclick = finish;
  const step = () => {
    if (i >= result.trace.length) return finish();
    appendEvent(list, result.trace[i++]);
    replayTimer = setTimeout(step, REPLAY_MS);
  };
  step();
}

function appendEvent(list, event) {
  const li = document.createElement("li");
  li.textContent = eventText(event);
  list.appendChild(li);
}

function setPostmortem(result) {
  const has = result !== null && result.postmortem !== null;
  $("postmortem").textContent = has ? result.postmortem : "Run an incident to see its draft.";
  $("publish").disabled = !has || result.published;
  $("export-md").disabled = !has;
  $("export-json").disabled = !has;
}

async function download(path, name) {
  const response = await fetch(path, { headers: { "X-Hub-Token": TOKEN } });
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

$("publish").addEventListener("click", async () => {
  $("pm-error").textContent = "";
  const { ok, data } = await api("POST", `/api/runs/${currentRun}/publish`, undefined);
  if (!ok) $("pm-error").textContent = describe(data);
  else setPostmortem(data);
});
$("export-md").addEventListener("click", () => download(`/api/runs/${currentRun}/postmortem.md`, "postmortem.md"));
$("export-json").addEventListener("click", () => download(`/api/runs/${currentRun}/postmortem.json`, "postmortem.json"));

$("play").addEventListener("click", async () => {
  $("play-status").textContent = "Running both...";
  $("play-clean").textContent = "";
  $("play-planted").textContent = "";
  const request = { alert_id: $("play-alert").value, text: $("play-text").value };
  const { ok, data } = await api("POST", "/api/playground", request);
  if (!ok) {
    $("play-status").textContent = describe(data);
    return;
  }
  const poll = async () => {
    const view = (await api("GET", `/api/runs/${data.run_id}`)).data;
    if (view.status === "running") return setTimeout(poll, POLL_MS);
    if (view.status === "error") {
      $("play-status").textContent = `Failed: ${view.error}`;
      return;
    }
    $("play-clean").textContent = view.result.clean_lines.join("\n");
    $("play-planted").textContent = view.result.planted_lines.join("\n");
    $("play-status").textContent = view.result.unchanged ? "DECISION lines unchanged." : "DECISION lines DIFFER.";
  };
  poll();
});

$("upload-btn").addEventListener("click", async () => {
  const errors = $("upload-errors");
  errors.replaceChildren();
  $("upload-ok").textContent = "";
  let body;
  try {
    body = JSON.parse($("upload").value);
  } catch (error) {
    errors.appendChild(Object.assign(document.createElement("li"), { textContent: `not valid JSON: ${error.message}` }));
    return;
  }
  const { ok, data } = await api("POST", "/api/uploads", body);
  if (ok) {
    $("upload-ok").textContent = `Added ${data.alert_id} on ${data.service}.`;
    loadAlerts();
    return;
  }
  for (const [field, message] of Object.entries(data.fields || {})) {
    errors.appendChild(Object.assign(document.createElement("li"), { textContent: `${field}: ${message}` }));
  }
  if (!Object.keys(data.fields || {}).length) {
    errors.appendChild(Object.assign(document.createElement("li"), { textContent: data.error }));
  }
});

$("upload").value = JSON.stringify(
  {
    service: {
      name: "billing-service",
      baseline_latency_ms: 150,
      baseline_error_rate: 0.01,
      latency: { kind: "step", base: 150, at: 1760172000, level: 1200 },
      error_rate: { kind: "flat", level: 0.01 },
      deployments: [{ at: 1760171400, version: "v3.1.0" }],
      dependencies: [],
      effects: { rollback_deployment: { success: 160, fix_fails: 3000 } },
    },
    alert: {
      alert_id: "UP-1",
      severity: "high",
      metric: "latency_ms",
      summary: "billing latency spike, error rate normal",
      fired_at: 1760172600,
    },
  },
  null,
  2,
);

loadAlerts();
