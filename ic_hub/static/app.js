"use strict";
// Every server string reaches the page through textContent; no HTML is ever built from it.

const TOKEN = document.querySelector('meta[name="hub-token"]').content;
const $ = (id) => document.getElementById(id);
const REPLAY_MS = 250;
const POLL_MS = 200;

let currentRun = null;
let liveSeq = 0; // highest trace event already drawn from the stream
let lastAlert = null;
let replayTimer = null;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Theme: follows the system until the person picks one; the choice is a per-browser convenience.
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const dark = theme === "dark";
  $("theme-btn").setAttribute("aria-pressed", String(dark));
  $("theme-btn").textContent = dark ? "Light theme" : "Dark theme";
  $("theme-btn").setAttribute("aria-label", dark ? "Use light theme (shortcut t)" : "Use dark theme (shortcut t)");
}

function currentTheme() {
  const set = document.documentElement.dataset.theme;
  if (set) return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  try {
    localStorage.setItem("hub-theme", next);
  } catch (error) {
    // storage may be blocked; the choice then lasts for this page only
  }
}

try {
  const saved = localStorage.getItem("hub-theme");
  if (saved === "dark" || saved === "light") document.documentElement.dataset.theme = saved;
} catch (error) {
  // storage may be blocked
}
applyTheme(currentTheme());
$("theme-btn").addEventListener("click", toggleTheme);
const finishedRuns = [];
const SVG_NS = "http://www.w3.org/2000/svg";

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
  $("ex-alert").replaceChildren();
  for (const a of data.alerts) {
    const row = document.createElement("tr");
    cell(row, a.alert_id);
    cell(row, a.service);
    cell(row, a.metric);
    cell(row, a.source);
    cell(row, a.summary);
    cell(row, a.labels ? Object.entries(a.labels).map(([k, v]) => `${k}=${v}`).join(", ") : "");
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
    $("ex-alert").appendChild(option.cloneNode(true));
  }
}

function runRequest(alertId) {
  const request = { alert_id: alertId, mode: $("mode").value, fix_outcome: $("fix").value };
  const deadline = $("deadline").value;
  if (deadline !== "") request.deadline_s = Number(deadline);
  const whatIf = [];
  if ($("wi-stale").checked) whatIf.push("stale_deployments");
  if ($("wi-tool").checked) whatIf.push("tool_failure");
  if (whatIf.length) request.what_if = whatIf;
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
  lastAlert = alertId;
  $("run-status").textContent = `Running ${alertId}...`;
  followRun(data.run_id);
}

function describe(data) {
  const fields = Object.entries(data.fields || {}).map(([k, v]) => `${k}: ${v}`);
  return [data.error, ...fields].join(" | ");
}

// Reads the approval stream with fetch, so the token header still applies. Resolves true if the
// stream opened (it ends when the run does, or after the server's time limit), false if it could not.
async function readStream(runId) {
  try {
    const response = await fetch(`/api/runs/${runId}/stream`, { headers: { "X-Hub-Token": TOKEN } });
    if (!response.ok || !response.body) return false;
    $("stream-status").textContent = "Live updates: stream.";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return true;
      if (runId !== currentRun) {
        reader.cancel();
        return true;
      }
      buffer += decoder.decode(value, { stream: true });
      let cut = buffer.indexOf("\n\n");
      while (cut >= 0) {
        handleStreamBlock(runId, buffer.slice(0, cut));
        buffer = buffer.slice(cut + 2);
        cut = buffer.indexOf("\n\n");
      }
    }
  } catch (error) {
    return false;
  }
}

function handleStreamBlock(runId, block) {
  const data = block.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("");
  if (!data || block.startsWith("event: end")) return;
  try {
    const view = JSON.parse(data);
    if (block.startsWith("event: trace")) return showLiveEvents(runId, view);
    if (view.status === "running") showApproval(runId, view.pending);
  } catch (error) {
    // a damaged event is skipped; the next fetch of the run is the source of truth
  }
}

async function followRun(runId) {
  let live = true;
  while (runId === currentRun) {
    if (live) live = await readStream(runId);
    if (!live) $("stream-status").textContent = "Live updates: polling.";
    const { ok, data } = await api("GET", `/api/runs/${runId}`);
    if (!ok || runId !== currentRun) return;
    showApproval(runId, data.pending);
    if (data.status === "error") {
      $("run-status").textContent = `Run failed: ${data.error}`;
      return;
    }
    if (data.status !== "running") {
      showResult(data.result);
      return;
    }
    if (!live) await sleep(POLL_MS);
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

function showLiveEvents(runId, events) {
  if (runId !== currentRun || !Array.isArray(events)) return;
  for (const event of events) {
    if (event.seq <= liveSeq) continue;
    appendEvent($("trace"), event);
    liveSeq = event.seq;
  }
}

function clearReplay() {
  clearTimeout(replayTimer);
  liveSeq = 0;
  $("trace").replaceChildren();
  $("decisions").textContent = "";
  $("skip").hidden = true;
  setPostmortem(null);
  renderChart(null);
}

function eventText(e) {
  const fields = Object.entries(e.fields).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : v}`);
  return `[t+${e.elapsed_s.toFixed(2)}s] ${e.kind} ${fields.join(" ")}`;
}

function showResult(result) {
  $("run-status").textContent = `Replaying the finished trace. Final state: ${result.state}`;
  renderChart(result.chart);
  rememberRun(currentRun);
  loadSimilar(currentRun);
  loadHistory();
  loadMetrics();
  const list = $("trace");
  let i = result.trace.filter((e) => e.seq <= liveSeq).length; // already drawn live
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

function textItem(list, text) {
  const li = document.createElement("li");
  li.textContent = text;
  list.appendChild(li);
}

async function loadHistory() {
  const { data } = await api("GET", "/api/history");
  $("history-off").hidden = data.enabled;
  $("history-on").hidden = !data.enabled;
  if (!data.enabled) return;
  $("history-error").textContent = data.write_error || "";
  const body = document.querySelector("#history tbody");
  body.replaceChildren();
  for (const r of data.runs) {
    const row = document.createElement("tr");
    cell(row, r.run_id);
    cell(row, r.alert_id);
    cell(row, r.service);
    cell(row, r.state);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "View";
    button.addEventListener("click", () => viewStored(r.run_id));
    cell(row, "").appendChild(button);
    body.appendChild(row);
  }
}

async function viewStored(runId) {
  const { ok, data } = await api("GET", `/api/history/${runId}`);
  if (!ok) {
    $("history-error").textContent = describe(data);
    return;
  }
  clearReplay();
  currentRun = null;
  const result = data.result;
  for (const event of result.trace) appendEvent($("trace"), event);
  $("decisions").textContent = result.decision_lines.join("\n");
  $("postmortem").textContent = result.postmortem || "No draft.";
  renderChart(result.chart);
  $("run-status").textContent = `Stored run ${runId}: ${result.state} (read only).`;
  loadSimilar(runId);
}

async function loadSimilar(runId) {
  const list = $("similar");
  list.replaceChildren();
  if (!runId) return;
  const { ok, data } = await api("GET", `/api/runs/${runId}/similar`);
  if (!ok || !data.enabled) return;
  if (!data.runs.length) textItem(list, "None yet.");
  for (const r of data.runs) textItem(list, `${r.run_id} ${r.alert_id} on ${r.service}: ${r.state} (${r.reason})`);
}

$("audit-btn").addEventListener("click", async () => {
  const { data } = await api("GET", "/api/audit");
  const v = data.verify;
  $("audit-status").textContent = v.ok
    ? `Chain intact: ${v.entries} entries. ${v.note}`
    : `CHAIN BROKEN at line ${v.first_bad_line}: ${v.reason}`;
  $("audit-out").textContent = data.entries
    .map((e) => `#${e.seq} ${e.event} ${Object.entries(e.detail).map(([k, x]) => `${k}=${x}`).join(" ")}`)
    .join("\n");
});

function svgEl(name, attrs, text) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderChart(chart) {
  const svg = $("chart");
  svg.replaceChildren();
  svg.hidden = !chart;
  if (!chart) {
    $("chart-desc").textContent = "No chart for this run.";
    return;
  }
  const W = 640, H = 240, L = 48, R = 12, T = 12, B = 30;
  const span = chart.window_end - chart.window_start || 1;
  const values = chart.points.map((p) => p[1]).concat([chart.baseline, chart.limit]);
  const top = Math.max(...values) * 1.1 || 1;
  const x = (t) => L + ((t - chart.window_start) / span) * (W - L - R);
  const y = (v) => H - B - (v / top) * (H - B - T);
  svg.appendChild(svgEl("line", { class: "axis", x1: L, y1: H - B, x2: W - R, y2: H - B }));
  svg.appendChild(svgEl("line", { class: "axis", x1: L, y1: T, x2: L, y2: H - B }));
  svg.appendChild(svgEl("text", { x: 4, y: T + 8 }, top.toPrecision(3)));
  svg.appendChild(svgEl("text", { x: 4, y: H - B }, "0"));
  svg.appendChild(svgEl("line", { class: "baseline", x1: L, y1: y(chart.baseline), x2: W - R, y2: y(chart.baseline) }));
  svg.appendChild(svgEl("line", { class: "limit", x1: L, y1: y(chart.limit), x2: W - R, y2: y(chart.limit) }));
  svg.appendChild(svgEl("text", { x: L + 4, y: y(chart.baseline) + 11 }, `baseline ${chart.baseline}`));
  svg.appendChild(svgEl("text", { x: L + 4, y: y(chart.limit) - 3 }, "verify limit (baseline x 1.10)"));
  const path = chart.points.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  svg.appendChild(svgEl("path", { class: "series", d: path }));
  const marks = [["fired", chart.fired_at], ["fix", chart.executed_at], ["verified", chart.verify_end]];
  for (const [label, t] of marks) {
    if (t === null) continue;
    svg.appendChild(svgEl("line", { class: "mark", x1: x(t), y1: T, x2: x(t), y2: H - B }));
    svg.appendChild(svgEl("text", { x: x(t) + 3, y: T + 18 }, label));
  }
  for (const d of chart.deployments) {
    const cx = x(d.at);
    svg.appendChild(svgEl("path", { class: "deploy", d: `M${cx} ${H - B - 9} l5 9 h-10 z` }));
    svg.appendChild(svgEl("text", { x: cx + 6, y: H - B - 12 }, d.version));
  }
  const last = chart.points[chart.points.length - 1];
  $("chart-desc").textContent =
    `${chart.service} ${chart.metric}: ${chart.points.length} samples, baseline ${chart.baseline}, ` +
    `last value ${last ? last[1] : "n/a"}, ${chart.deployments.length} deployment(s) in the window.`;
}

function rememberRun(runId) {
  if (finishedRuns[finishedRuns.length - 1] === runId) return;
  finishedRuns.push(runId);
  if (finishedRuns.length > 2) finishedRuns.shift();
  $("diff-btn").disabled = finishedRuns.length < 2;
}

$("diff-btn").addEventListener("click", async () => {
  const { ok, data } = await api("POST", "/api/diff", { a: finishedRuns[0], b: finishedRuns[1] });
  if (!ok) {
    $("diff").textContent = describe(data);
    return;
  }
  const lines = [
    `state: ${data.state[0]} -> ${data.state[1]}`,
    `handoff: ${data.handoff_reason[0]} -> ${data.handoff_reason[1]}`,
    data.same_decisions ? "DECISION lines: identical" : "DECISION lines: differ",
    ...data.only_in_a.map((l) => `- ${l}`),
    ...data.only_in_b.map((l) => `+ ${l}`),
    data.same_trace_kinds ? "trace kinds: identical" : "trace kinds differ",
  ];
  $("diff").textContent = lines.join("\n");
});

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

async function pollJob(runId, status, onDone) {
  const view = (await api("GET", `/api/runs/${runId}`)).data;
  if (view.status === "running") return setTimeout(() => pollJob(runId, status, onDone), POLL_MS);
  if (view.status === "error") {
    status.textContent = `Failed: ${view.error}`;
    return;
  }
  onDone(view.result);
}

$("ex-llm").addEventListener("change", () => {
  const hosted = $("ex-llm").value === "hosted";
  $("ex-warn").hidden = !hosted;
  $("ex-ack-row").hidden = !hosted;
  if (!hosted) $("ex-ack").checked = false;
});

$("ex-btn").addEventListener("click", async () => {
  $("ex-out").textContent = "";
  $("ex-status").textContent = "Asking...";
  const request = {
    alert_id: $("ex-alert").value,
    question: $("ex-question").value,
    llm: $("ex-llm").value,
    acknowledge_remote: $("ex-ack").checked,
  };
  const { ok, data } = await api("POST", "/api/explain", request);
  if (!ok) {
    $("ex-status").textContent = describe(data);
    return;
  }
  pollJob(data.run_id, $("ex-status"), (result) => {
    $("ex-out").textContent = result.lines.join("\n");
    const sent = result.remote ? " The question and facts were sent to the hosted service." : "";
    const note = result.configured ? "" : ` Not configured on the server (missing ${result.missing.join(", ")}).`;
    $("ex-status").textContent = `Status: ${result.status}.${sent}${note}`;
  });
});

function evalText(r) {
  const lines = [
    `llm: ${r.llm}${r.configured ? "" : ` (not configured: missing ${r.missing.join(", ")})`}`,
    `golden: ${r.golden_passed}/${r.golden.length} passed`,
    ...r.golden.map((g) => `  ${g.golden_id} ${g.alert_id} verdict=${g.verdict} runbook=${g.runbook} action=${g.action} passed=${g.passed}`),
    `attack: unchanged=${r.attack.unchanged} inputs_identical=${r.attack.inputs_identical} decision_lines_identical=${r.attack.decision_lines_identical}`,
    ...r.attack.variants.map(([name, ok]) => `  ${name} unchanged=${ok}`),
    `naive baseline: wrong on ${r.naive_wrong} of ${r.naive.length}`,
    ...r.x3.map((x) => `x3 ${x.alert_id} advisor=${x.advisor} narrator=${x.narrator} explainer=${x.explainer} order=${x.order.join(",")} identical=${x.identical}`),
    `decisions_changed=${r.decisions_changed}`,
  ];
  return lines.join("\n");
}

$("eval-btn").addEventListener("click", async () => {
  $("eval-out").textContent = "";
  $("eval-status").textContent = "Running the evaluation...";
  const request = { llm: $("eval-llm").value, acknowledge_remote: $("eval-ack").checked };
  const { ok, data } = await api("POST", "/api/evaluate", request);
  if (!ok) {
    $("eval-status").textContent = describe(data);
    return;
  }
  pollJob(data.run_id, $("eval-status"), (result) => {
    $("eval-out").textContent = evalText(result);
    $("eval-status").textContent = result.decisions_changed === 0 ? "Done. No decision changed." : "Done. A DECISION line CHANGED.";
  });
});

function showErrors(list, data) {
  for (const [field, message] of Object.entries(data.fields || {})) textItem(list, `${field}: ${message}`);
  if (!Object.keys(data.fields || {}).length) textItem(list, data.error);
}

// Posts the JSON in a textarea; returns the response, or null after showing a parse error.
async function submitJson(box, errors, path) {
  errors.replaceChildren();
  let body;
  try {
    body = JSON.parse(box.value);
  } catch (error) {
    textItem(errors, `not valid JSON: ${error.message}`);
    return null;
  }
  const reply = await api("POST", path, body);
  if (!reply.ok) showErrors(errors, reply.data);
  return reply;
}

$("upload-btn").addEventListener("click", async () => {
  $("upload-ok").textContent = "";
  const reply = await submitJson($("upload"), $("upload-errors"), "/api/uploads");
  if (reply && reply.ok) {
    $("upload-ok").textContent = `Added ${reply.data.alert_id} on ${reply.data.service}.`;
    loadAlerts();
    loadMetrics();
  }
});

$("am-btn").addEventListener("click", async () => {
  $("am-ok").textContent = "";
  const reply = await submitJson($("am-json"), $("am-errors"), "/api/intake/alertmanager");
  if (reply && reply.ok) {
    $("am-ok").textContent = reply.data.alerts.map((a) => `${a.status} ${a.alert_id} on ${a.service}`).join("; ");
    loadAlerts();
    loadMetrics();
  }
});

async function loadMetrics() {
  const { ok, data } = await api("GET", "/api/metrics");
  if (!ok) return;
  const pairs = [
    ["runs started", data.runs_started],
    ["running", data.runs_running],
    ["done", data.runs_done],
    ["failed", data.runs_failed],
    ["mean run (s)", data.mean_run_s === null ? "n/a" : data.mean_run_s],
    ["alerts via Alertmanager", data.intake_alerts],
    ["uploads", data.uploads],
    ...Object.entries(data.states).map(([k, v]) => [`ended ${k}`, v]),
    ...Object.entries(data.approvals).map(([k, v]) => [`approval ${k}`, v]),
  ];
  const strip = $("metrics");
  strip.replaceChildren();
  for (const [label, value] of pairs) {
    const li = document.createElement("li");
    const number = document.createElement("strong");
    number.textContent = String(value);
    li.appendChild(number);
    li.appendChild(document.createTextNode(label));
    strip.appendChild(li);
  }
  strip.title = data.scope;
}

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target;
  if (target instanceof HTMLElement && target.matches("input, textarea, select")) return;
  const asking = !$("approval").hidden;
  if (event.key === "r" && lastAlert) startRun(lastAlert);
  else if (event.key === "t") toggleTheme();
  else if (event.key === "?") $("shortcuts").open = !$("shortcuts").open;
  else if (event.key === "A" && asking) $("approve").click();
  else if (event.key === "D" && asking) $("deny").click();
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

$("am-json").value = JSON.stringify(
  {
    version: "4",
    status: "firing",
    receiver: "incident-hub",
    alerts: [
      {
        status: "firing",
        labels: { alertname: "HighLatency", service: "checkout-service", severity: "critical" },
        annotations: { summary: "checkout latency is high" },
        startsAt: "2026-10-21T09:00:00Z",
        fingerprint: "a1b2c3d4e5f60718",
      },
    ],
  },
  null,
  2,
);

loadAlerts();
loadHistory();
loadMetrics();
