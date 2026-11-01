# City click-to-place fire — 2026-11-01

The shared cloud toolbar now says **Add fire**. In a live controller session,
choose Size/Heat, select Add fire, then click/tap the ground or a building in the
RGB picture. Escape cancels placement mode. The coordinate form remains available.

The pre-existing `ignite` command and native surface picker are retained. This
change hardens the interaction: contain/letterbox mapping, primary-pointer taps,
drag/cancel rejection, a placement marker, one pending fire per client, fresh-frame
and connection guards, and request-ID-correlated application/rejection feedback.
The UI waits for native `command_results` instead of treating a queue ACK as success.
Retries reuse the same request ID; spectator authentication and command bounds remain.

Native picks use the latest rendered camera and conservative mission obstacle
boxes/terrain, not exact architectural triangle picking or a frame-synchronized
depth buffer. Moving views and video delay can affect placement accuracy. Fires
edit scenario world truth through `SwarmMission.add_fire`, never actor ledgers.
Physical release remains disabled.

Verification: `node tools/test_cloud_fire.cjs` passes actual UI handler checks for
placement, mobile letterboxing, matching confirmations/rejections, duplicate
clicks, drag/right-click/cancel and stale/offline guards. The targeted pytest run
(`test_cloud_control.py`, `test_city_live.py`, `test_swarm_mission.py`) passes 81
tests; the full suite passes 148 tests (one existing dependency deprecation
warning). Ruff on `embernet tests` and cloud/perception JS parser checks pass.
Browser inspected the deployed offline page: Add fire is visible and disabled;
no JavaScript errors. No live GPU click/visual acceptance was run in this change.

Deployment: CPU gateway updated; simulator image `im-8cjvF5noBMU9pv8CRlnL2T`
built and one 600-second city voucher prepared. Preparation starts no GPU. The
existing private control invite is preserved and excluded from release material.
Free-credit guard passed with zero billed cost. Session state must be checked
again before allocating anything; this document is not live billing/state.

Final read-only check found a newly active session `live-80c4b90bcaa9`, frame 161,
phase `Swarm mission active`, with the new `command_results` field. It was left
running; no fire was injected by this change. The public JS hash matches the
tested local file. Evidence: `artifacts/embernet/cloud/click-fire-source-check.json`.
