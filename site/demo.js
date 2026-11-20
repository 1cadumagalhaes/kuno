const pods = [
  { name: "storefront-7d9f", ready: "1/1", status: "Running", restarts: "0", age: "12m", cpu: "24m", memory: "48Mi" },
  { name: "catalog-55bd", ready: "1/1", status: "Running", restarts: "0", age: "18m", cpu: "31m", memory: "72Mi" },
  { name: "checkout-2a10", ready: "1/1", status: "Running", restarts: "1", age: "24m", cpu: "42m", memory: "96Mi" },
  { name: "worker-6f83", ready: "1/1", status: "Running", restarts: "0", age: "31m", cpu: "18m", memory: "40Mi" },
];

const logLines = [
  '2026-11-19T14:31:02Z {"level":"info","logger":"catalog","message":"cache hit","namespace":"storefront","ttl":60}',
  '[web] 2026-11-19T14:31:03Z {"level":"warning","msg":"slow upstream","duration_ms":812,"route":"/products"}',
  "2026-11-19T14:31:05Z INFO  health check passed",
  '2026-11-19T14:31:08Z {"level":"error","logger":"checkout","message":"payment declined","order":"A-1932","code":"card_declined"}',
  '2026-11-19T14:31:11Z {"level":"debug","component":"pool","message":"connection ready","size":8}',
];
const LOG_KEY_GROUPS = [
  ["timestamp", "time", "ts", "@timestamp"],
  ["level", "severity", "lvl"],
  ["message", "msg"],
  ["category", "logger", "component", "module"],
];
const LOG_USED_KEYS = new Set(LOG_KEY_GROUPS.flat());
const manifest = [
  "apiVersion: v1",
  "kind: Pod",
  "metadata:",
  "  name: storefront-7d9f",
  "  namespace: storefront",
  "  labels:",
  "    app: storefront",
  "    tier: frontend",
  "spec:",
  "  containers:",
  "    - name: web",
  "      image: example.invalid/storefront:1.4.2",
  "      ports:",
  "        - containerPort: 8080",
];
const events = [
  "NORMAL  Scheduled   2m  Successfully assigned storefront/storefront-7d9f to node-a",
  "NORMAL  Pulled      2m  Container image already present on machine",
  "NORMAL  Started     2m  Started container web",
  "WARN    BackOff     8m  Back-off restarting failed container api",
];

const english = {
  filterPods: "Filter pods",
  filterLogs: "Filter logs",
  search: (view) => `Search ${view}`,
  noRows: "No pods match that filter.",
  noSelection: "No pod matches this filter.",
  openPod: 'Press <kbd>Enter</kbd> to open this pod\'s containers.',
  readyPod: 'Container <code>web</code> is ready. Press <kbd>Esc</kbd> to go back.',
  pods: (count) => `${count} ${count === 1 ? "pod" : "pods"}`,
  logs: (count, mode) => `${count} ${count === 1 ? "line" : "lines"} · ${mode} mode`,
  emptyLogs: "No log lines match that filter.",
  yaml: "pod/storefront-7d9f · YAML",
  events: (count) => `${count} events · storefront`,
  help: "keyboard guide",
  container: (name) => `container/web · ${name}`,
  unknown: (command) => `Unknown demo command: ${command || "(empty)"}`,
  copied: "Copied.",
  copyFallback: "Select and copy the command.",
  viewLabels: { pods: "pods", logs: "logs", yaml: "yaml", events: "events" },
  helpText: "NAVIGATION\n  j / ↓       Move down\n  k / ↑       Move up\n  Enter       Open selected pod\n\nACTIONS\n  l           Open logs\n  m           Toggle raw / pretty logs\n  y           View YAML\n  Ctrl+E      View events\n  :logs       Use the command bar\n\nPress Esc or choose a view to return.",
};
const t = Object.assign({}, english, window.KUNO_I18N || {});

const demo = document.querySelector("#demo-main");
const rows = document.querySelector("#demo-rows");
const output = document.querySelector("#demo-output");
const logPanel = document.querySelector("#log-panel");
const logOutput = document.querySelector("#log-output");
const logModes = [...document.querySelectorAll(".log-mode")];
const filter = document.querySelector("#demo-filter");
const commandBar = document.querySelector("#demo-command");
const commandInput = document.querySelector("#demo-command-input");
const status = document.querySelector("#demo-status");
const info = document.querySelector("#demo-info");
const tabs = [...document.querySelectorAll(".demo-tab")];
let view = "pods";
let logMode = "raw";
let selected = 0;
let expanded = false;
let query = "";

function setStatus(message) { status.textContent = message; }
function selectedPod() {
  const index = filteredPods()[selected];
  return index === undefined ? null : pods[index];
}
function filteredPods() {
  const needle = query.trim().toLowerCase();
  return pods.map((pod, index) => ({ pod, index }))
    .filter(({ pod }) => !needle || pod.name.toLowerCase().includes(needle) || pod.status.toLowerCase().includes(needle))
    .map(({ index }) => index);
}
function renderInfo() {
  const pod = selectedPod();
  if (!pod) {
    document.querySelector("#info-name").textContent = "-";
    document.querySelector("#info-cpu").textContent = "-";
    document.querySelector("#info-memory").textContent = "-";
    document.querySelector("#info-note").textContent = t.noSelection;
    return;
  }
  document.querySelector("#info-name").textContent = pod.name;
  document.querySelector("#info-cpu").textContent = pod.cpu;
  document.querySelector("#info-memory").textContent = pod.memory;
  document.querySelector("#demo-crumb").textContent = t.viewLabels[view] ?? view;
  document.querySelector("#info-note").innerHTML = expanded ? t.readyPod : t.openPod;
}
function parseLogLine(line) {
  let prefix = "";
  let payload = line;
  const prefixMatch = payload.match(/^(\[[^\]]+\])\s+(.*)$/);
  if (prefixMatch) [prefix, payload] = prefixMatch.slice(1);
  let external = null;
  const timestampMatch = payload.match(/^(\d{4}-\d{2}-\d{2}T\S+)\s+(\{.*\})$/);
  if (timestampMatch) [external, payload] = timestampMatch.slice(1);
  let data;
  try { data = JSON.parse(payload); } catch { return { raw: line, data: null }; }
  if (!data || typeof data !== "object" || Array.isArray(data)) return { raw: line, data: null };
  const firstString = (keys) => {
    for (const key of keys) {
      if (typeof data[key] === "string" && data[key]) return data[key];
    }
    return null;
  };
  // Field order follows the JSON object, as the app's parser does; only nested values are sorted.
  const fields = Object.keys(data)
    .filter((key) => !LOG_USED_KEYS.has(key))
    .map((key) => [key, data[key]]);
  return {
    raw: line,
    data,
    prefix,
    timestamp: firstString(LOG_KEY_GROUPS[0]) ?? external,
    level: firstString(LOG_KEY_GROUPS[1]),
    message: firstString(LOG_KEY_GROUPS[2]),
    category: firstString(LOG_KEY_GROUPS[3]),
    fields,
  };
}

function fieldValue(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function shortTimestamp(timestamp) {
  const parts = timestamp.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (!parts) return timestamp.slice(0, 19);
  const [, , month, day, hour, minute, second] = parts;
  const zone = /(Z|[+-]\d{2}:?\d{2})$/.test(timestamp);
  if (!zone) return `${month}-${day} ${hour}:${minute}:${second}`;
  const date = new Date(`${timestamp.slice(0, 19)}Z`);
  const pad = (value) => String(value).padStart(2, "0"); // taste-skill-ignore: log timestamps, not labels
  return `${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;
}

function logLevelClass(level) {
  const value = level.toLowerCase();
  if (["error", "fatal", "critical"].includes(value)) return "is-error";
  if (["warn", "warning"].includes(value)) return "is-warn";
  if (value === "debug") return "is-debug";
  return "is-info";
}

function structuredLogText(parsed) {
  const parts = [];
  if (parsed.prefix) parts.push(parsed.prefix);
  if (parsed.timestamp) parts.push(shortTimestamp(parsed.timestamp));
  if (parsed.level) parts.push(parsed.level.toUpperCase());
  if (parsed.category) parts.push(parsed.category);
  if (parsed.message) parts.push(parsed.message);
  for (const [key, value] of parsed.fields) parts.push(`${key}=${fieldValue(value)}`);
  return parts.join(" ");
}

function appendStructuredLog(container, parsed) {
  const add = (text, className) => {
    const span = document.createElement("span");
    if (className) span.className = className;
    span.textContent = text;
    container.append(span);
  };
  if (parsed.prefix) { add(parsed.prefix, "log-prefix"); container.append(" "); }
  if (parsed.timestamp) { add(shortTimestamp(parsed.timestamp), "log-time"); container.append(" "); }
  if (parsed.level) {
    add(parsed.level.toUpperCase(), `log-level ${logLevelClass(parsed.level)}`);
    container.append(" ");
  }
  if (parsed.category) { add(parsed.category, "log-category"); container.append(" "); }
  if (parsed.message) add(parsed.message);
  for (const [key, value] of parsed.fields) {
    container.append(" ");
    add(key, "log-key");
    container.append(`=${fieldValue(value)}`);
  }
}

function visibleLogLines() {
  const needle = query.trim().toLowerCase();
  return logLines
    .map((line) => (logMode === "pretty" ? parseLogLine(line) : { raw: line, data: null }))
    .filter((parsed) => {
      if (!needle) return true;
      const text = parsed.data ? structuredLogText(parsed) : parsed.raw;
      return text.toLowerCase().includes(needle);
    });
}

function renderLogs() {
  document.querySelector(".demo-table-heading").hidden = true;
  rows.hidden = true;
  output.hidden = true;
  info.hidden = true;
  logPanel.hidden = false;
  logOutput.replaceChildren();
  const visible = visibleLogLines();
  for (const parsed of visible) {
    const line = document.createElement("div");
    line.className = "log-line";
    if (parsed.data) appendStructuredLog(line, parsed);
    else line.textContent = parsed.raw;
    logOutput.append(line);
  }
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "demo-empty";
    empty.textContent = t.emptyLogs;
    logOutput.append(empty);
  }
  document.querySelector(".demo-filter input").placeholder = t.filterLogs;
  setStatus(t.logs(visible.length, logMode));
}

function setLogMode(next) {
  logMode = next === "pretty" ? "pretty" : "raw";
  for (const button of logModes) {
    const active = button.dataset.mode === logMode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  if (view === "logs") renderLogs();
}

function renderPods() {
  document.querySelector(".demo-table-heading").hidden = false;
  rows.hidden = false;
  output.hidden = true;
  logPanel.hidden = true;
  info.hidden = false;
  rows.replaceChildren();
  const indices = filteredPods();
  if (selected >= indices.length) selected = Math.max(0, indices.length - 1);
  for (const [visibleIndex, index] of indices.entries()) {
    const pod = pods[index];
    const row = document.createElement("button");
    row.type = "button";
    row.className = "demo-row";
    row.setAttribute("aria-current", String(visibleIndex === selected));
    row.setAttribute("aria-label", `${pod.name}, ${pod.status}, ${pod.ready} ready`);
    row.innerHTML = `<span class="pod-name"></span><span></span><span class="pod-status"></span><span></span><span></span>`;
    const cells = row.querySelectorAll("span");
    [pod.name, pod.ready, pod.status, pod.restarts, pod.age].forEach((value, cell) => { cells[cell].textContent = value; });
    row.addEventListener("click", () => { selected = visibleIndex; expanded = false; render(); demo.focus(); });
    rows.append(row);
  }
  if (!indices.length) {
    const empty = document.createElement("p");
    empty.className = "demo-empty";
    empty.textContent = t.noRows;
    rows.append(empty);
  }
  document.querySelector(".demo-filter input").placeholder = t.filterPods;
  document.querySelector(".demo-table-heading span:first-child").textContent = "NAME";
  renderInfo();
  setStatus(t.pods(indices.length));
}
function renderOutput(lines, message) {
  document.querySelector(".demo-table-heading").hidden = true;
  rows.hidden = true;
  output.hidden = false;
  logPanel.hidden = true;
  info.hidden = true;
  output.textContent = lines.join("\n");
  document.querySelector(".demo-filter input").placeholder = view === "logs" ? t.filterLogs : t.search(view);
  setStatus(message);
}
function render() {
  tabs.forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-pressed", String(active));
  });
  document.querySelector("#demo-crumb").textContent = t.viewLabels[view] ?? view;
  if (view === "pods") renderPods();
  if (view === "logs") renderLogs();
  if (view === "yaml") renderOutput(manifest.filter((line) => line.toLowerCase().includes(query.toLowerCase())), t.yaml);
  if (view === "events") renderOutput(events.filter((line) => line.toLowerCase().includes(query.toLowerCase())), t.events(events.filter((line) => line.toLowerCase().includes(query.toLowerCase())).length));
}
function setView(next) {
  if (!["pods", "logs", "yaml", "events"].includes(next)) return;
  view = next;
  expanded = false;
  query = "";
  filter.value = "";
  render();
}
function showHelp() {
  view = "help";
  tabs.forEach((tab) => { tab.classList.remove("is-active"); tab.setAttribute("aria-pressed", "false"); });
  document.querySelector(".demo-table-heading").hidden = true;
  rows.hidden = true;
  info.hidden = true;
  logPanel.hidden = true;
  output.hidden = false;
  output.textContent = t.helpText;
  setStatus(t.help);
}
filter.addEventListener("input", () => { query = filter.value; selected = 0; render(); });
tabs.forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
logModes.forEach((button) => button.addEventListener("click", () => setLogMode(button.dataset.mode)));

demo.addEventListener("keydown", (event) => {
  if (event.target === filter || event.target === commandInput) return;
  const indices = filteredPods();
  const key = event.key.toLowerCase();
  if (view === "pods" && (key === "arrowdown" || key === "j")) {
    event.preventDefault(); selected = Math.min(selected + 1, Math.max(indices.length - 1, 0)); expanded = false; render(); demo.focus({ preventScroll: true });
  } else if (view === "pods" && (key === "arrowup" || key === "k")) {
    event.preventDefault(); selected = Math.max(selected - 1, 0); expanded = false; render(); demo.focus({ preventScroll: true });
  } else if (key === "enter" && view === "pods") {
    event.preventDefault();
    const pod = selectedPod();
    if (!pod) return;
    expanded = !expanded;
    document.querySelector("#info-note").innerHTML = expanded ? t.readyPod : t.openPod;
    setStatus(expanded ? t.container(pod.name) : t.pods(indices.length));
  } else if (event.ctrlKey && key === "e") { event.preventDefault(); setView("events"); }
  else if (key === "l") setView("logs");
  else if (key === "m" && view === "logs") { event.preventDefault(); setLogMode(logMode === "raw" ? "pretty" : "raw"); }
  else if (key === "y") setView("yaml");
  else if (key === "?" || (event.shiftKey && key === "/")) showHelp();
  else if (key === "/") { event.preventDefault(); filter.focus(); }
  else if (key === ":") { event.preventDefault(); commandBar.hidden = false; commandInput.focus(); }
  else if (key === "escape") {
    if (view === "help") setView("pods");
    else if (expanded) { expanded = false; renderInfo(); setStatus(t.pods(indices.length)); }
    else { commandBar.hidden = true; demo.focus(); }
  }
});

commandInput.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { commandBar.hidden = true; demo.focus(); }
  if (event.key === "Enter") {
    const command = commandInput.value.trim().replace(/^:/, "").split(/\s+/)[0];
    if (["pods", "logs", "yaml", "events"].includes(command)) setView(command);
    else setStatus(t.unknown(command));
    commandInput.value = "";
    commandBar.hidden = true;
    demo.focus();
  }
});
document.querySelector("#reset-demo").addEventListener("click", () => {
  selected = 0; expanded = false; query = ""; filter.value = ""; commandInput.value = "";
  commandBar.hidden = true; setView("pods"); demo.focus();
});
document.querySelector("#copy-install").addEventListener("click", async () => {
  const status = document.querySelector("#copy-status");
  try {
    await navigator.clipboard.writeText("uv tool install kuno");
    status.textContent = t.copied;
  } catch {
    status.textContent = t.copyFallback;
    const range = document.createRange();
    range.selectNodeContents(document.querySelector(".install-command code"));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
});

document.querySelectorAll(".badge-row img").forEach((badge) => {
  badge.addEventListener("error", () => {
    const fallback = document.createElement("span");
    fallback.className = "badge-fallback";
    fallback.textContent = badge.alt;
    badge.closest("a").replaceChildren(fallback);
  });
});

render();
