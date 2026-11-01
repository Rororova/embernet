const $ = (id) => document.getElementById(id);
let report,
  visible = [],
  current;
const pct = (x) => `${(100 * x).toFixed(1)}%`;
const url = (path) =>
  "/evidence/" + path.split("/").map(encodeURIComponent).join("/");
function show(frame) {
  current = frame;
  const position = visible.indexOf(frame);
  $("sample-position").textContent =
    `OBSERVATION ${String(position + 1).padStart(2, "0")} / ${visible.length}`;
  $("frame-title").textContent = frame.id
    .replace("fire-", "Fire / ")
    .replace("clear-", "No fire / ");
  $("observation-rgb").src = url(frame.overlay);
  $("observation-thermal").src = url(frame.thermal_preview);
  $("original-rgb").href = url(frame.rgb);
  $("frame-size").textContent = `${frame.width} × ${frame.height}`;
  const strongest = frame.detections.reduce(
    (best, d) => (!best || d.confidence > best.confidence ? d : best),
    null,
  );
  $("fire-confidence").textContent = strongest
    ? `${pct(strongest.confidence)} ${strongest.kind}`
    : "No detection";
  $("temperature-max").textContent = `${frame.thermal_stats.max.toFixed(1)}°C`;
  $("hot-fraction").textContent = pct(frame.thermal_stats.hot_fraction);
  $("inference-latency").textContent = `${Math.round(frame.latency_ms)} ms`;
  $("observation-details").textContent =
    `Source label: ${frame.source_label}. ${frame.captured_at_raw ? `Raw camera timestamp: ${frame.captured_at_raw} (timezone unspecified).` : "Capture timestamp unavailable."} ${frame.timestamp_warning || ""} RGB confidence threshold: ${pct(report.confidence)}.`;
  $("detection-list").replaceChildren();
  if (!frame.detections.length)
    $("detection-list").textContent =
      "No fire or smoke detections above threshold.";
  for (const detection of frame.detections) {
    const row = document.createElement("div");
    row.className = "detection-row";
    const name = document.createElement("span"),
      score = document.createElement("span");
    name.textContent = detection.kind;
    score.textContent = pct(detection.confidence);
    row.append(name, score);
    $("detection-list").append(row);
  }
  for (const button of $("sample-list").querySelectorAll("button"))
    button.setAttribute("aria-current", String(button.dataset.id === frame.id));
  $("previous").disabled = position <= 0;
  $("next").disabled = position >= visible.length - 1;
}
function filter() {
  const mode = $("sample-filter").value;
  visible = report.frames.filter(
    (f) =>
      mode === "all" ||
      (mode === "missed"
        ? f.source_label === "Fire" && !f.predicted_warning
        : f.source_label === mode),
  );
  $("sample-count").textContent = visible.length;
  $("sample-list").replaceChildren();
  for (const frame of visible) {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      "sample-button" +
      ((frame.source_label === "Fire") !== frame.predicted_warning
        ? " missed"
        : "");
    button.dataset.id = frame.id;
    button.setAttribute("aria-label", `Inspect ${frame.id}`);
    const image = document.createElement("img");
    image.src = url(frame.rgb);
    image.alt = "";
    image.loading = "lazy";
    const text = document.createElement("span"),
      name = document.createElement("strong"),
      state = document.createElement("small");
    name.textContent = frame.id;
    state.textContent = frame.predicted_warning
      ? frame.predicted_fire
        ? "Fire detected"
        : "Smoke detected"
      : frame.source_label === "Fire"
        ? "RGB fire missed"
        : "No RGB warning";
    text.append(name, state);
    button.append(image, text);
    button.onclick = () => show(frame);
    $("sample-list").append(button);
  }
  document.querySelector(".frame-panel").hidden = !visible.length;
  $("no-matches").hidden = !!visible.length;
  if (visible.length) show(visible.includes(current) ? current : visible[0]);
}
$("sample-filter").onchange = filter;
$("previous").onclick = () => show(visible[visible.indexOf(current) - 1]);
$("next").onclick = () => show(visible[visible.indexOf(current) + 1]);
try {
  const response = await fetch("/api/perception");
  if (!response.ok) throw Error("Evidence service is unavailable.");
  report = await response.json();
  if (!report.ready) throw Error("No recorded observations are loaded yet.");
  const rows = [
    ["Fire-source warning recall", (s) => pct(s.recall)],
    ["Precision", (s) => pct(s.precision)],
    ["No-fire specificity", (s) => pct(s.specificity)],
    ["Fire-source samples without warning", (s) => `${s.fn} / 24`],
    ["No-fire false alarms", (s) => `${s.fp} / 24`],
  ];
  for (const [title, format] of rows) {
    const row = document.createElement("tr");
    for (const text of [
      title,
      format(report.rgb_image_level),
      format(report.thermal_source_label_agreement),
    ]) {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.append(cell);
    }
    $("benchmark-rows").append(row);
  }
  const modelName = report.model.repo || "EMBERNET real-data fine-tune";
  const modelRevision = report.model.revision || report.model.run_id;
  const onnxHash =
    report.model.files?.["model.onnx"]?.sha256 || report.model_sha256;
  $("provenance-details").textContent =
    `Model: ${modelName} · revision ${modelRevision} · AGPL-3.0. Dataset v${report.dataset_version}: publisher reports MIT. Flame-only detections: ${report.rgb_flame_only.tp} / 24 fire samples; RGB warnings above include smoke. ONNX SHA-256: ${onnxHash}. Median processing: ${report.latency_ms.median} ms; p95: ${report.latency_ms.p95} ms (${report.latency_ms.provider}).`;
  $("flame-only-note").textContent =
    `The RGB model detected flames in ${report.rgb_flame_only.tp} / 24 fire samples. Its warnings here came from smoke detections and require verification.`;
  $("review-content").hidden = false;
  filter();
} catch (error) {
  $("review-error").hidden = false;
  $("review-error").textContent = error.message;
}
