import { ForestView } from "./forest3d.js";
const $ = (id) => document.getElementById(id);
const canvas = $("map");
let sceneView;
let state = null,
  selected = "E02",
  tool = null,
  toastTimer,
  lastCamera = -1,
  lastCameraDrone = null,
  fleetSignature = "",
  busy = false;
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const clock = (t) =>
  `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
function toast(text) {
  $("toast").textContent = text;
  $("toast").classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("visible"), 3500);
}
async function api(path, data) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json();
    throw Error(
      typeof error.detail === "string"
        ? error.detail
        : "Check the entered mission settings.",
    );
  }
  return response.json();
}
async function action(path, data, message) {
  try {
    await api(path, data);
    if (message) toast(message);
    await refresh();
  } catch (error) {
    toast(error.message);
  }
}
function setTool(value) {
  tool = tool === value ? null : value;
  document
    .querySelectorAll("[data-tool]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.tool === tool)),
    );
  $("map-instruction").textContent = tool
    ? `CLICK TO PLACE ${tool.toUpperCase()} · ESC TO CANCEL`
    : "SELECT AN AIRCRAFT TO INSPECT ITS KNOWLEDGE";
  $("add-coordinate").textContent = `Add ${tool || "fire"} at coordinates`;
  canvas.style.cursor = tool ? "crosshair" : "default";
}
function selectAircraft(id) {
  selected = id;
  lastCamera = -1;
  render();
  draw();
}
document
  .querySelectorAll("[data-tool]")
  .forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && tool) setTool(tool);
});
$("launch").onclick = () =>
  action("/api/control", { action: state?.paused ? "launch" : "pause" });
$("reset").onclick = () =>
  action(
    "/api/reset",
    {
      seed: Number($("seed").value),
      drones: Number($("fleet").value),
      sensor: $("sensor").value,
      policy: $("policy").value,
    },
    "Mission reset. Launch to begin.",
  );
$("speed").onchange = () =>
  action("/api/control", { action: "speed", value: Number($("speed").value) });
$("mesh").onchange = () =>
  action(
    "/api/control",
    { action: "mesh", value: $("mesh").checked },
    $("mesh").checked
      ? "Mesh restored"
      : "Mesh disabled. Drones use their local knowledge.",
  );
$("loss").oninput = () => {
  $("loss-value").textContent = `${Math.round($("loss").value * 100)}%`;
};
$("loss").onchange = () =>
  action("/api/control", { action: "loss", value: Number($("loss").value) });
$("severity").oninput = () => {
  $("severity-value").textContent = Number($("severity").value).toFixed(2);
};
$("isolate").onclick = () =>
  action("/api/control", { action: "isolate", value: selected });
function addIncident(x, y) {
  return action(
    "/api/incidents",
    {
      kind: tool || "fire",
      x,
      y,
      severity: Number($("severity").value),
      radius: 5,
    },
    `${tool || "Fire"} added. Drones must detect it before responding.`,
  );
}
$("add-coordinate").onclick = () =>
  addIncident(Number($("coord-x").value), Number($("coord-y").value));
["show-mesh", "show-sensors", "show-truth"].forEach(
  (id) =>
    ($(id).onchange = () => {
      document.querySelector(".truth-label").textContent = $("show-truth")
        .checked
        ? "Simulator truth visible"
        : "Reported incident estimates";
      draw();
    }),
);
function render() {
  if (!state) return;
  const drone = state.drones.find((d) => d.id === selected) || state.drones[0];
  selected = drone.id;
  $("clock").textContent = clock(state.time);
  if (document.activeElement !== $("speed"))
    $("speed").value = String(state.speed);
  $("run-status").textContent = state.paused ? "PAUSED" : "LIVE";
  $("launch").querySelector("span").textContent = state.paused
    ? state.time
      ? "Resume mission"
      : "Launch swarm"
    : "Pause mission";
  $("launch").querySelector("svg").innerHTML = state.paused
    ? '<path d="m6 3 11 7-11 7Z"/>'
    : '<path d="M5 3h4v14H5zm7 0h4v14h-4z"/>';
  $("run-description").textContent =
    `Seed ${state.seed} · ${state.drones.length} aircraft · Synthetic forest`;
  document.querySelector(".mission-name .muted").textContent =
    `/ ${state.seed}`;
  $("active-fires").textContent = String(
    state.truth.fires.filter((f) => f.remaining > 0.2).length,
  ).padStart(2, "0");
  $("contained").textContent = String(state.metrics.contained).padStart(2, "0");
  $("people").textContent = String(state.metrics.survivor_responses).padStart(
    2,
    "0",
  );
  $("water").textContent = state.metrics.water_used.toFixed(1);
  $("mode-note").textContent =
    `${state.sensor_mode.startsWith("learned") ? "Synthetic-trained vision prototype" : state.sensor_mode} · ${state.policy_mode}`;
  $("error").hidden = !state.error;
  $("error").textContent = state.error
    ? `Mission paused: ${state.error}. Reset the mission to recover.`
    : "";
  $("recording-status").textContent = state.viewer_error
    ? "Rerun recording active · viewer unavailable"
    : "Rerun recording active";
  const signature = state.drones.map((d) => d.id).join(",");
  if (signature !== fleetSignature) {
    fleetSignature = signature;
    $("fleet-list").innerHTML = state.drones
      .map(
        (d) =>
          `<button class="fleet-button ${d.id === selected ? "active" : ""}" data-drone="${d.id}" aria-pressed="${d.id === selected}" aria-label="Inspect aircraft ${d.id}"><i></i>${d.id}</button>`,
      )
      .join("");
    document.querySelectorAll("[data-drone]").forEach(
      (b) =>
        (b.onclick = () => {
          selectAircraft(b.dataset.drone);
        }),
    );
  }
  document.querySelectorAll("[data-drone]").forEach((b) => {
    b.classList.toggle("active", b.dataset.drone === selected);
    b.setAttribute("aria-pressed", String(b.dataset.drone === selected));
  });
  $("selected-name").textContent = selected;
  $("selected-task").textContent = drone.task.toUpperCase();
  $("decision-reason").textContent = drone.reason;
  $("battery").textContent = `${Math.round(drone.battery * 100)}%`;
  $("battery-meter").value = drone.battery;
  $("tank").textContent = `${drone.water.toFixed(1)} L`;
  $("water-meter").max = state.config.max_water;
  $("water-meter").value = drone.water;
  $("peers").textContent = drone.peer_count;
  $("altitude").textContent = `${Math.round(drone.position[2])} m AGL`;
  $("isolate").textContent = state.mesh.isolated.includes(selected)
    ? "Restore radio"
    : "Isolate radio";
  $("ledger-description").textContent =
    `${selected}’s local knowledge. Updated by its sensors and delivered reports.`;
  const incidents = drone.incidents
    .filter((i) => !["cleared", "merged"].includes(i.status))
    .sort(
      (a, b) =>
        b.survivor * 100 +
        b.severity * 12 -
        (a.survivor * 100 + a.severity * 12),
    );
  $("incident-count").textContent = incidents.length;
  if (incidents.length) {
    $("incidents").innerHTML = incidents
      .map((i) => {
        const commits = drone.commitments.filter(
          (c) => c.incident_id === i.id && c.acknowledged,
        );
        const demand =
          i.kind === "fire"
            ? Math.max(2, i.extent * i.extent * 0.38 + i.severity * 4)
            : 0;
        return `<article class="incident"><div class="incident-heading"><h3>${esc(i.id)}</h3><span>${esc(i.status.toUpperCase())}</span></div>${i.survivor ? '<p class="survivor">Possible person · highest urgency</p>' : i.animal ? '<p class="survivor">Animal evidence reported</p>' : ""}<div class="incident-facts"><div><small>Severity estimate</small>${i.severity.toFixed(2)}</div><div><small>Report age</small>${Math.max(0, state.time - i.observed_at).toFixed(0)} s</div><div><small>Agent estimate</small>${demand.toFixed(1)} L</div><div><small>Acknowledged</small>${commits.length} aircraft</div></div><p class="commitment">${commits.length ? commits.map((c) => `${esc(c.drone_id)} · ETA ${Math.max(0, c.eta).toFixed(0)}s`).join(" / ") : "No acknowledged responders"}</p>${i.deferred_reason ? `<p>${esc(i.deferred_reason)}</p>` : ""}</article>`;
      })
      .join("");
  } else {
    $("incidents").innerHTML =
      `<div class="empty"><svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="16"/><path d="M24 14v10l7 5M7 7l5 5m24 24 5 5"/></svg><h3>${state.time ? "No active reports" : "Awaiting observations"}</h3><p>${state.time ? "This aircraft has no active incident reports. Cleared records remain in the exported replay." : "Launch the swarm to begin searching. An incident appears here when this aircraft sees it or receives a report."}</p></div>`;
  }
  $("event-log").innerHTML = state.events.length
    ? [...state.events]
        .reverse()
        .slice(0, 18)
        .map(
          (e) =>
            `<div class="event"><time>${clock(e.time)}</time><span class="event-drone">${esc(e.drone)}</span><span class="event-kind">${esc(e.kind)}</span><span>${esc(e.text)}</span></div>`,
        )
        .join("")
    : '<p class="event-empty">The mission is ready. Launch the swarm to record its first decisions.</p>';
  $("mesh-summary").textContent = state.mesh.enabled
    ? `${state.mesh.links.length} direct links · ${Math.round(state.mesh.loss * 100)}% packet loss`
    : "MESH OFFLINE · local autonomy continues";
  $("packet-summary").textContent =
    `${state.mesh.stats.delivered} delivered / ${state.mesh.stats.lost} lost`;
  $("mesh").checked = state.mesh.enabled;
  if (
    selected !== lastCameraDrone ||
    state.time - lastCamera >= 1.5 ||
    lastCamera < 0
  ) {
    lastCameraDrone = selected;
    lastCamera = state.time;
    $("rgb").src = `/api/camera/${selected}/rgb?t=${state.time}`;
    $("thermal").src = `/api/camera/${selected}/thermal?t=${state.time}`;
  }
  $("sensor").querySelector("[value=learned]").disabled = !state.models.vision;
  $("policy").querySelector("[value=learned]").disabled = !state.models.mission;
}
function draw() {
  if (state && sceneView)
    sceneView.update(state, selected, tool, {
      mesh: $("show-mesh").checked,
      sensors: $("show-sensors").checked,
      truth: $("show-truth").checked,
    });
}
sceneView = new ForestView(canvas, {
  onSelect: selectAircraft,
  onPlace: addIncident,
  onReady: () => {
    $("scene-loading").hidden = true;
    draw();
    sceneView.setMode("follow");
  },
  onError: (error) => {
    $("scene-loading").hidden = false;
    $("scene-loading").textContent =
      `3D view unavailable: ${error.message}. Reload or use a WebGL2-capable browser.`;
  },
});
sceneView.onModeChange = (mode) =>
  document
    .querySelectorAll("[data-camera]")
    .forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.camera === mode),
      ),
    );
document
  .querySelectorAll("[data-camera]")
  .forEach(
    (button) =>
      (button.onclick = () => sceneView.setMode(button.dataset.camera)),
  );
$("panel-toggle").onclick = () => {
  document.body.classList.toggle("controls-open");
  $("panel-toggle").setAttribute(
    "aria-expanded",
    String(document.body.classList.contains("controls-open")),
  );
};
$("scene-expand").onclick = () => {
  document.body.classList.toggle("scene-focus");
  $("scene-expand").textContent = document.body.classList.contains(
    "scene-focus",
  )
    ? "Exit focus"
    : "Focus view";
};
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    document.body.classList.remove("scene-focus");
    $("scene-expand").textContent = "Focus view";
  }
});
async function refresh() {
  if (busy) return;
  busy = true;
  try {
    const response = await fetch("/api/state");
    if (!response.ok) throw Error("Mission control is unavailable");
    state = await response.json();
    render();
    draw();
  } catch (error) {
    $("error").hidden = false;
    $("error").textContent =
      `Connection lost. Start EMBERNET and this page will reconnect automatically. ${error.message}`;
  } finally {
    busy = false;
  }
}
new ResizeObserver(() => draw()).observe(canvas);
refresh();
setInterval(refresh, 650);
