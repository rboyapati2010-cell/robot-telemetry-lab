"use strict";
const $ = (id) => document.getElementById(id),
  NS = "http://www.w3.org/2000/svg";
const state = { runs: [], thresholds: {} };
let primary = null,
  compare = null,
  left = null,
  right = null,
  comparison = null,
  sensor = "velocity",
  busy = false;
const sensors = {
  velocity: { title: "Velocity tracking", key: "velocity_mps", unit: "m/s" },
  battery: { title: "Battery voltage", key: "battery_v", unit: "V" },
  current: { title: "Motor current", key: "motor_current_a", unit: "A" },
  temperature: { title: "Motor temperature", key: "temperature_c", unit: "°C" },
};
const metricRows = [
  ["mae_mps", "Tracking MAE", "m/s"],
  ["rmse_mps", "Tracking RMSE", "m/s"],
  ["peak_error_mps", "Peak tracking error", "m/s"],
  ["min_battery_v", "Minimum battery", "V"],
  ["peak_current_a", "Peak current", "A"],
  ["peak_temperature_c", "Peak temperature", "°C"],
  ["duration_s", "Duration", "s"],
];
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text != null) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function svgNode(tag, attrs, text) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs || {}))
    el.setAttribute(key, String(value));
  if (text != null) el.textContent = text;
  return el;
}
function source(run) {
  return run.source === "synthetic_demo" ? "Synthetic example" : "Imported CSV";
}
function num(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : "—";
}
function note(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = "notice" + (error ? " error" : "");
  $("notice").hidden = false;
  $("notice").setAttribute("role", error ? "alert" : "status");
}
async function api(path, body) {
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), 20000);
  try {
    const options = {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    };
    if (body !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        data.message || data.error || "The request could not be completed.",
      );
    return data;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "The server took too long. Check the local server and try again.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "Could not reach the local server. Check that TraceDrive is running, then retry.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
function controls() {
  document.querySelectorAll("button").forEach((button) => {
    if (button.classList.contains("run-button")) {
      // Keep saved-run controls focusable during the request. act() guards
      // activation while busy, and aria-disabled communicates that state.
      button.disabled = false;
      button.setAttribute("aria-disabled", String(busy));
    } else {
      button.disabled = busy;
    }
  });
  document
    .querySelectorAll("select")
    .forEach((select) => (select.disabled = busy));
  $("seed-button").disabled = busy || state.runs.length > 0;
  $("upload-form").setAttribute("aria-busy", String(busy));
}
async function act(fn) {
  if (busy) return;
  busy = true;
  controls();
  try {
    await fn();
  } catch (error) {
    note(error.message, true);
  } finally {
    busy = false;
    controls();
  }
}
function selectOptions(select, includeEmpty) {
  select.replaceChildren();
  if (includeEmpty) select.append(new Option("No comparison", ""));
  for (const run of state.runs) {
    if (includeEmpty && run.id === primary) continue;
    select.append(new Option(run.name, run.id));
  }
}
function renderShell() {
  const list = $("run-list");
  // Reuse keyed buttons so selecting a run never removes the focused node.
  const existing = new Map(
    [...list.children].map((button) => [button.dataset.runId, button]),
  );
  for (const [index, run] of state.runs.entries()) {
    const button = existing.get(run.id) || node("button", null, "run-button");
    existing.delete(run.id);
    button.type = "button";
    button.dataset.runId = run.id;
    button.setAttribute("aria-pressed", String(primary === run.id));
    button.replaceChildren(
      node("strong", run.name),
      node(
        "span",
        num(run.duration_s, 1) + " s · " + run.sample_count + " samples",
      ),
      node("span", source(run)),
    );
    button.onclick = () =>
      act(async () => {
        primary = run.id;
        if (compare === primary) compare = null;
        renderShell();
        await loadSelection();
      });
    if (list.children[index] !== button) {
      list.insertBefore(button, list.children[index] || null);
    }
  }
  for (const obsolete of existing.values()) obsolete.remove();
  $("no-runs").hidden = !!state.runs.length;
  $("empty-workspace").hidden = !!state.runs.length;
  $("analysis").hidden = !state.runs.length;
  const hasExample = state.runs.some((run) => run.source === "synthetic_demo");
  $("seed-button").textContent = hasExample
    ? "Example runs loaded"
    : state.runs.length
      ? "Workspace has imported runs"
      : "Load example runs";
  $("seed-button").title = state.runs.length
    ? "Existing runs are preserved. Load examples in an empty workspace."
    : "";
  selectOptions($("baseline-select"), false);
  selectOptions($("compare-select"), true);
  $("baseline-select").value = primary || "";
  $("compare-select").value = compare || "";
  controls();
}
async function refresh(options = {}) {
  Object.assign(state, await api("/api/state"));
  if (!state.runs.some((run) => run.id === primary))
    primary =
      (
        state.runs.find((run) =>
          run.name.toLowerCase().startsWith("baseline"),
        ) ||
        state.runs[0] ||
        {}
      ).id || null;
  if (options.autoCompare && !compare)
    compare = (state.runs.find((run) => run.id !== primary) || {}).id || null;
  if (compare === primary || !state.runs.some((run) => run.id === compare))
    compare = null;
  renderShell();
  await loadSelection();
}
async function loadSelection() {
  if (!primary) {
    left = right = comparison = null;
    return;
  }
  const requests = [api("/api/runs/" + encodeURIComponent(primary))];
  if (compare) {
    requests.push(api("/api/runs/" + encodeURIComponent(compare)));
    requests.push(
      api(
        "/api/compare?left=" +
          encodeURIComponent(primary) +
          "&right=" +
          encodeURIComponent(compare),
      ),
    );
  }
  const result = await Promise.all(requests);
  left = result[0];
  right = result[1] || null;
  comparison = result[2] || null;
  renderAnalysis();
}
function renderAnalysis() {
  if (!left) return;
  const origins = [source(left.run)];
  if (right && source(right.run) !== origins[0])
    origins.push(source(right.run));
  $("data-origin").textContent = origins.join(" + ");
  $("sample-count").textContent =
    left.samples.length.toLocaleString() +
    " samples" +
    (right ? " + " + right.samples.length.toLocaleString() : "");
  $("metric-left").title = left.run.name;
  $("metric-right").hidden = !right;
  $("metric-delta").hidden = !right;
  $("metric-right").title = right ? right.run.name : "";
  const table = $("metrics-body");
  table.replaceChildren();
  for (const [key, label, unit] of metricRows) {
    const a =
      key === "duration_s" ? left.run.duration_s : left.run.metrics[key];
    const b = right
      ? key === "duration_s"
        ? right.run.duration_s
        : right.run.metrics[key]
      : null;
    const tr = node("tr");
    tr.append(
      node("td", label, "metric-name"),
      node("td", num(a) + " " + unit, "amount"),
    );
    if (right) {
      const delta = comparison.deltas[key];
      tr.append(
        node("td", num(b) + " " + unit, "amount"),
        node("td", (delta > 0 ? "+" : "") + num(delta) + " " + unit, "amount"),
      );
    }
    table.append(tr);
  }
  renderAnomalies();
  renderChart();
}
function renderAnomalies() {
  const list = $("anomaly-list");
  list.replaceChildren();
  const kinds = {
    tracking_error: "Tracking error",
    low_battery: "Low battery",
    high_current: "High current",
    high_temperature: "High temperature",
  };
  let count = 0;
  for (const detail of [left, right].filter(Boolean)) {
    const start = detail.samples[0].time_s;
    for (const item of detail.anomalies) {
      count++;
      const block = node("div", null, "anomaly-item");
      const heading = node("div", null, "anomaly-title");
      heading.append(
        node("span", kinds[item.kind] || item.kind),
        node(
          "span",
          num(item.start_s - start, 1) +
            "–" +
            num(item.end_s - start, 1) +
            " s",
        ),
      );
      block.append(heading, node("p", detail.run.name + " · " + item.detail));
      list.append(block);
    }
  }
  $("anomaly-count").textContent = count + " segments";
  if (!count)
    list.append(
      node(
        "div",
        "No samples crossed the configured thresholds in the selected runs.",
        "anomaly-empty",
      ),
    );
  const t = state.thresholds;
  $("threshold-description").textContent =
    "Illustrative thresholds: error > " +
    t.tracking_error_mps +
    " m/s; battery < " +
    t.battery_v +
    " V; current > " +
    t.current_a +
    " A; temperature > " +
    t.temperature_c +
    " °C. Crossings do not establish a hardware fault.";
}

// Retain the low and high point of each bucket in time order. Full samples
// remain available for inspection; only the drawn line is reduced.
function displayPoints(samples, key, limit = 1000) {
  if (samples.length <= limit) return samples;
  const result = [samples[0]],
    size = Math.ceil((samples.length - 2) / Math.floor((limit - 2) / 2));
  for (let start = 1; start < samples.length - 1; start += size) {
    const end = Math.min(samples.length - 1, start + size);
    let low = start,
      high = start;
    for (let i = start + 1; i < end; i++) {
      if (samples[i][key] < samples[low][key]) low = i;
      if (samples[i][key] > samples[high][key]) high = i;
    }
    if (low === high) result.push(samples[low]);
    else {
      result.push(samples[Math.min(low, high)], samples[Math.max(low, high)]);
    }
  }
  result.push(samples[samples.length - 1]);
  return result;
}
function nearestSample(samples, elapsed) {
  const time = elapsed + samples[0].time_s;
  let lo = 0,
    hi = samples.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (samples[mid].time_s < time) lo = mid + 1;
    else hi = mid;
  }
  return lo > 0 &&
    Math.abs(samples[lo - 1].time_s - time) <
      Math.abs(samples[lo].time_s - time)
    ? lo - 1
    : lo;
}
function renderChart() {
  const holder = $("plot");
  holder.replaceChildren();
  if (!left || !left.samples.length) return;
  const spec = sensors[sensor],
    width = Math.max(310, holder.clientWidth - 30),
    height = width < 500 ? 245 : 315;
  const margin = { left: 56, right: 19, top: 25, bottom: 44 },
    plotW = width - margin.left - margin.right,
    plotH = height - margin.top - margin.bottom;
  const series = [];
  for (const [detail, color, targetColor, role] of [
    [left, "#185e4c", "#707d83", "Primary"],
    [right, "#bb622c", "#6d76a3", "Comparison"],
  ]) {
    if (!detail) continue;
    if (sensor === "velocity")
      series.push({
        detail,
        key: "target_velocity_mps",
        color: targetColor,
        dashed: true,
        label: role + " target",
      });
    series.push({
      detail,
      key: spec.key,
      color,
      dashed: false,
      label: role + " " + (sensor === "velocity" ? "measured" : spec.unit),
    });
  }
  let min = Infinity,
    max = -Infinity,
    xMax = 0;
  for (const s of series) {
    const samples = s.detail.samples;
    xMax = Math.max(
      xMax,
      samples[samples.length - 1].time_s - samples[0].time_s,
    );
    for (const point of samples) {
      min = Math.min(min, point[s.key]);
      max = Math.max(max, point[s.key]);
    }
  }
  const pad = (max - min) * 0.12 || Math.max(Math.abs(max) * 0.1, 0.2);
  min -= pad;
  max += pad;
  if (sensor === "velocity" || sensor === "current") min = Math.min(0, min);
  xMax = Math.max(xMax, 0.001);
  const x = (time) => margin.left + (time / xMax) * plotW,
    y = (value) => margin.top + ((max - value) / (max - min)) * plotH;
  const chart = svgNode("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img",
    tabindex: "0",
    "aria-label":
      spec.title +
      " over elapsed time in seconds. Use left and right arrow keys to inspect the primary run.",
  });
  chart.append(
    svgNode(
      "title",
      {},
      spec.title + " — primary" + (right ? " and comparison" : "") + " run",
    ),
    svgNode(
      "desc",
      {},
      "Each run starts at elapsed time zero. The horizontal axis is elapsed seconds. The vertical axis is " +
        spec.unit +
        ". Values are drawn from the loaded CSV data.",
    ),
  );
  chart.append(
    svgNode("text", { x: margin.left, y: 14, class: "axis-label" }, spec.unit),
  );
  for (let i = 0; i <= 4; i++) {
    const value = min + ((max - min) * i) / 4,
      yy = y(value);
    chart.append(
      svgNode("line", {
        x1: margin.left,
        x2: width - margin.right,
        y1: yy,
        y2: yy,
        stroke: "#e2e8e4",
        "stroke-width": 1,
      }),
    );
    chart.append(
      svgNode(
        "text",
        { x: margin.left - 9, y: yy + 4, "text-anchor": "end" },
        num(value, max - min < 4 ? 2 : 1),
      ),
    );
  }
  for (let i = 0; i <= 5; i++) {
    const time = (xMax * i) / 5;
    chart.append(
      svgNode(
        "text",
        { x: x(time), y: height - 24, "text-anchor": "middle" },
        num(time, xMax < 10 ? 1 : 0),
      ),
    );
  }
  chart.append(
    svgNode(
      "text",
      {
        x: margin.left + plotW / 2,
        y: height - 5,
        "text-anchor": "middle",
        class: "axis-label",
      },
      "Elapsed time (s)",
    ),
  );
  const legend = $("legend");
  legend.replaceChildren();
  for (const s of series) {
    const start = s.detail.samples[0].time_s,
      points = displayPoints(s.detail.samples, s.key);
    const attrs = {
      d: points
        .map(
          (p, i) =>
            (i ? "L" : "M") +
            x(p.time_s - start).toFixed(2) +
            "," +
            y(p[s.key]).toFixed(2),
        )
        .join(" "),
      fill: "none",
      stroke: s.color,
      "stroke-width": s.dashed ? 1.7 : 2.1,
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
    };
    if (s.dashed) attrs["stroke-dasharray"] = "5 5";
    chart.append(svgNode("path", attrs));
    const item = node("span"),
      mark = svgNode("svg", { viewBox: "0 0 23 9", "aria-hidden": "true" }),
      line = svgNode("line", {
        x1: 0,
        x2: 23,
        y1: 4.5,
        y2: 4.5,
        stroke: s.color,
        "stroke-width": 2,
      });
    if (s.dashed) line.setAttribute("stroke-dasharray", "5 3");
    mark.append(line);
    item.append(mark, document.createTextNode(s.label));
    legend.append(item);
  }
  let probeIndex = 0;
  const crosshair = svgNode("line", {
    x1: margin.left,
    x2: margin.left,
    y1: margin.top,
    y2: height - margin.bottom,
    stroke: "#7b8a82",
    "stroke-width": 1,
    "stroke-dasharray": "3 4",
    visibility: "hidden",
  });
  const dot = svgNode("circle", {
    cx: 0,
    cy: 0,
    r: 4,
    fill: "#185e4c",
    stroke: "white",
    "stroke-width": 1.5,
    visibility: "hidden",
  });
  chart.append(crosshair, dot);
  function inspect(index) {
    probeIndex = Math.max(0, Math.min(left.samples.length - 1, index));
    const sample = left.samples[probeIndex],
      elapsed = sample.time_s - left.samples[0].time_s,
      xx = x(elapsed);
    crosshair.setAttribute("x1", xx);
    crosshair.setAttribute("x2", xx);
    crosshair.setAttribute("visibility", "visible");
    dot.setAttribute("cx", xx);
    dot.setAttribute("cy", y(sample[spec.key]));
    dot.setAttribute("visibility", "visible");
    let label =
      num(elapsed, 2) +
      " s · Primary " +
      num(sample[spec.key], 3) +
      " " +
      spec.unit;
    if (sensor === "velocity")
      label += " · target " + num(sample.target_velocity_mps, 3) + " m/s";
    if (right) {
      const last =
        right.samples[right.samples.length - 1].time_s -
        right.samples[0].time_s;
      if (elapsed <= last) {
        const other = right.samples[nearestSample(right.samples, elapsed)];
        label +=
          " · Comparison " +
          num(other[spec.key], 3) +
          " " +
          spec.unit +
          " (nearest sample)";
      }
    }
    $("probe-readout").textContent = label;
  }
  chart.addEventListener("pointermove", (event) => {
    const rect = chart.getBoundingClientRect(),
      px = ((event.clientX - rect.left) * width) / rect.width;
    inspect(
      nearestSample(
        left.samples,
        Math.max(0, Math.min(xMax, ((px - margin.left) / plotW) * xMax)),
      ),
    );
  });
  chart.addEventListener("focus", () => inspect(probeIndex));
  chart.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      inspect(
        probeIndex +
          (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 10 : 1),
      );
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      inspect(event.key === "Home" ? 0 : left.samples.length - 1);
    }
  });
  holder.append(chart);
  $("chart-title").textContent = spec.title;
  $("probe-readout").textContent =
    "Point at the chart, or focus it and use arrow keys, to inspect a sample.";
}

async function seedExamples() {
  await act(async () => {
    const result = await api("/api/demo/seed", {});
    await refresh({ autoCompare: true });
    note(
      result.seeded
        ? "Loaded two synthetic example runs. These measurements were generated for demonstration."
        : "Existing runs were preserved. Examples are only added to an empty workspace.",
    );
  });
}
$("seed-button").onclick = seedExamples;
$("empty-seed").onclick = seedExamples;
$("import-button").onclick = () => {
  $("upload-details").open = true;
  $("run-name").focus();
};
$("csv-file").onchange = () => {
  const file = $("csv-file").files[0];
  if (file && !$("run-name").value.trim())
    $("run-name").value = file.name.replace(/\.csv$/i, "").slice(0, 100);
};
$("upload-form").onsubmit = (event) => {
  event.preventDefault();
  act(async () => {
    const file = $("csv-file").files[0];
    if (!file) throw new Error("Choose a CSV file to import.");
    if (file.size > 4 * 1024 * 1024)
      throw new Error(
        "This file is too large. Use a CSV under 4 MB and up to 20,000 samples.",
      );
    const name = $("run-name").value.trim();
    if (!name) throw new Error("Give this run a name.");
    const result = await api("/api/runs", { name, csv: await file.text() });
    primary = result.run.id;
    if (compare === primary) compare = null;
    await refresh();
    $("upload-form").reset();
    note(
      "Imported " +
        result.run.name +
        ". All measurements and threshold crossings come from your CSV.",
    );
  });
};
$("baseline-select").onchange = () =>
  act(async () => {
    primary = $("baseline-select").value;
    if (compare === primary) compare = null;
    renderShell();
    await loadSelection();
  });
$("compare-select").onchange = () =>
  act(async () => {
    compare = $("compare-select").value || null;
    await loadSelection();
  });
document.querySelectorAll("[data-sensor]").forEach((button) => {
  button.onclick = () => {
    sensor = button.dataset.sensor;
    document
      .querySelectorAll("[data-sensor]")
      .forEach((tab) =>
        tab.setAttribute("aria-pressed", String(tab === button)),
      );
    renderChart();
  };
});
let resizeFrame = 0,
  lastWidth = 0;
new ResizeObserver((entries) => {
  const width = entries[0].contentRect.width;
  if (Math.abs(width - lastWidth) < 1) return;
  lastWidth = width;
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => renderChart());
}).observe($("plot"));
act(() => refresh({ autoCompare: true }));
