---
name: EMBERNET Mission Control
description: Live forest scenery with restrained field instrumentation for a research swarm simulator.
colors:
  bg: "#111b22"
  panel: "#17252d"
  panel2: "#1c2d35"
  line: "#30434b"
  text: "#e7e9e3"
  muted: "#a2b6bd"
  accent: "#eda66d"
  green: "#a6c3a0"
  blue: "#9bc7db"
typography:
  headline:
    fontFamily: "Rajdhani, sans-serif"
    fontSize: "34px"
    fontWeight: 600
    lineHeight: 1.1
  title:
    fontFamily: "Rajdhani, sans-serif"
    fontSize: "19px"
    fontWeight: 600
  body:
    fontFamily: '"Segoe UI", sans-serif'
    fontSize: "14px"
    lineHeight: 1.5
  metric:
    fontFamily: "Consolas, monospace"
    fontSize: "22px"
rounded:
  field: "4px"
  control: "5px"
spacing:
  control-x: "12px"
  control-y: "8px"
  panel-x: "15px"
  panel-y: "12px"
  workspace: "15px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#24221d"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  button-default:
    backgroundColor: "{colors.panel2}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
---
# Design System: EMBERNET Mission Control

## Overview

**Creative North Star: "Swarm Field Lab"**

A live, recognizable forest scene leads the interactive experience; slate instrumentation supports operation and evidence inspection. Detailed suppression quadrotors, conifers, terrain, field-station structures, people, fire, smoke and water make the simulation readable in space. Optional native Rerun supplies telemetry/replay, using Mesh3D arrays decoded from the same GLBs. Rerun's website examples remain the user's visual quality reference. The separate recorded-observations page lets real RGB and thermal imagery lead an evidence review using the same instrument vocabulary.

**Key Characteristics:**

- Detailed authored geometry, physical lighting, shadows and atmospheric depth.
- Tonal panels, fine dividers, restrained copper actions, and a settings drawer.
- Condensed headings, familiar body text, and monospaced telemetry.
- Persistent aircraft selection and clearly labeled local knowledge.
- Side-by-side source observations, explicit detection errors and inspectable provenance.

## Colors

Primary copper (`accent`) marks the run action, incident tools, and event categories. Secondary mineral blue (`blue`) marks aircraft selection and focus. Pale sage (`green`) supports radio/status cues, acknowledgments, and resource meters. Neutral slate (`bg`, `panel`, `panel2`) separates workspace layers; `line` divides them; `text` and `muted` establish reading hierarchy. Natural forest greens, earth tones, pale sky, warm flames and grey smoke belong to the 3D world; its materials are separate from instrument status colors.

Recorded observations use copper for fire and blue for smoke, paired with explicit class names. Thermal previews have a labeled 10–150°C display scale; measurements retain the original source values beyond that range. Never substitute the preview colors for measured temperature.

**The State Redundancy Rule.** Pair color with labels, identifiers, outlines, or pressed state; selection and operational meaning must remain explicit.

## Typography

Bundled Rajdhani SemiBold supplies headings and the wordmark; Segoe UI supplies controls and prose; Consolas supplies clocks, coordinates, quantities, and telemetry. The wordmark reduces to 28px on narrow screens; the selected-aircraft heading is 23px. Supporting labels range from 10–12px; scene/camera captions are compact (8–10px). Numeric summaries use tabular figures. Maintain visible units and avoid compressing primary instructions into caption text.

## Layout

The settings drawer starts closed so the main scene receives the first viewport. Desktop places the flexible scene above aircraft inspection, with a 285px ledger alongside and decision events below. Opening settings adds a 224px left rail. Main content has no fixed maximum width. Focus view hides secondary instrumentation while preserving the top bar and camera controls; Escape exits it.

The scene is 560px tall on desktop, growing to 650px with a 310px ledger from 1650px. At 1100px the scene becomes 510px tall, the open drawer narrows, and overlay toggles are hidden. At 850px scene, aircraft, ledger and events stack; open settings become a two-column area above them. At 640px the scene remains 480px tall, camera controls wrap, and model thumbnails sit below aircraft details. Preserve coordinate-entry and fleet-button alternatives to canvas interaction.

Recorded observations use a 1600px maximum-width workspace: a 190px sample rail, paired RGB/thermal figures, four measurement cells, explanatory notes, benchmark table and expandable provenance. At 1000px the rail narrows and measurements use two columns. At 650px samples become a horizontal strip, image pairs stack, and the benchmark becomes one column. Preserve image aspect ratio and source resolution labels; use contain rather than cropping evidence.

## Elevation & Depth

Panels are flat, with tonal differences and fine borders defining hierarchy. Spatial texture and depth belong to the rendered world: authored GLBs, sun and ambient lighting, soft shadows, haze and animated effects. Only the fixed confirmation toast uses a panel drop shadow. Scene captions use text shadows for legibility. Button backgrounds and toast opacity transition briefly (150ms); reduced-motion preferences disable these CSS transitions, while the live 3D renderer remains animated.

## Shapes

Workspace panels have square corners; fields and count badges have gently rounded corners; buttons and toast are slightly softer. Fine strokes structure the instruments. Aircraft use recognizable airframes with four rotor assemblies, camera pod, suppressant tank, nozzle and landing gear. Forest and subject geometry carry the scene; compact labels and estimate overlays supplement them. Marker-only scenery is a rejected presentation.

## Components

The copper primary button carries launch/pause/resume. Default buttons use raised slate; secondary actions use transparent fills. Selected placement tools retain copper borders and warm dark fills; selected fleet buttons retain blue borders and lighter slate fills. Hover brightens backgrounds, keyboard focus uses a blue outline (2px, 4px offset), and disabled buttons fade.

Fields use dark inset fills and visible labels; ranges expose their numeric output. Fleet buttons are persistent inspection navigation. Resource meters pair sage fills with exact quantities. Panels use divided headers and bounded scrolling for ledgers/logs. Empty ledgers explain how observations arrive; errors use an alert region, and confirmations use a polite live toast. Decision reasons and log entries describe actual simulator state and events.

Overview supports orbit/zoom, Follow drone frames the selected aircraft, and Scene POV supplies a scene camera. Camera controls expose pressed state. The scene opens in follow mode after assets load. Focus view enlarges the world; the settings button exposes its expanded state. Loading and WebGL failures use a visible status layer.

**The Evidence Boundary Rule.** Keep simulator truth, selected-aircraft reports, and model inputs visibly distinct. MODEL RGB INPUT and MODEL IR INPUT thumbnails show the procedural images consumed by the current CNN; Scene POV does not. Fire/smoke are visual models, and water appears only for recorded simulated discharge. Shared GLBs improve Rerun's geometry without turning presentation quality into real-data perception evidence.

Recorded-observation navigation exposes the current sample, previous/next controls and filters with an explicit empty state. RGB overlays sit beside source-TIFF thermal previews; source labels, strongest detection class, temperature, hot-pixel fraction and measured processing time remain visible. Benchmark copy distinguishes smoke warnings from flame detection: this sample produced smoke warnings on 24/24 fire and 3/24 no-fire samples, with 0/24 flame detections. Show raw timestamps and the unverified camera-clock warning; sample navigation does not imply a flight timeline. Thermal label agreement does not establish independent accuracy or calibrated severity.

## Do's and Don'ts

- **Do** preserve distinct simulator-truth and selected-aircraft knowledge labels.
- **Do** keep units, timestamps, acknowledgment wording, and synthetic camera captions visible.
- **Do** preserve persistent selection, keyboard focus, and narrow-screen wrapping.
- **Do** keep recognizable scene geometry and usable overview/follow/POV framing central.
- **Do** retain source labels, raw capture dates, clock warnings, modality labels and benchmark limitations on recorded observations.
- **Don't** introduce dashboard decoration that competes with task controls or evidence.
- **Don't** present estimated resources, learned decisions, or people reached as guarantees.
- **Don't** imply the 3D scene camera feeds the CNN or that FLAME 3 training is implemented.
- **Don't** present smoke warnings as successful flame detection or independent frames as a verified flight timeline.

Source: `embernet/ui/index.html`, `style.css`, `scene.css`, `app.js`, `forest3d.js`, `perception.html`, `perception.css`, `perception.js`, and `Start-EMBERNET.ps1`. Component previews and extensions: `.impeccable/design.json`. Current evidence: `context/REAL_PERCEPTION.md`. Recorded-observation captures: `artifacts/embernet/release-review/real-observations-desktop.png` and `real-observations-pair.png`. Independent UI review found no material blocker; final native Rerun visual verification remains pending.
