# Incident memory and priority

## User's motivating case

A drone committed to a large fire detects a smaller fire en route. It should
consider whether its existing response still needs it, compare other drones'
arrival times, and remember the smaller fire if it postpones responding.
Possible survivors rank above fire size alone.

## Implemented record and extension points

- Stable incident ID, estimated location/extent and positional uncertainty.
- Fire severity estimate, trend, confidence, sensor provenance, observation time.
- Human/animal evidence with confidence, location and observation time.
- Estimated suppression demand and uncertainty; visual size alone is not a
  calibrated physical water requirement.
- Status: suspected, verifying, confirmed, assigned, deferred, monitoring,
  escalated, or cleared with supporting evidence.
- Received responder commitments: drone, committed quantity, estimated arrival,
  commitment/version ID, acknowledgement and expiry.
- Deferral reason, next review time, last request and last received update.

Core fields are in contracts.Incident/Commitment and memory.IncidentLedger.
Explicit spatial uncertainty, learned growth forecasts and separate per-subject
evidence history remain extensions. Preserve provenance and
observation times across forwarding; message arrival must not make old evidence
fresh. Reconcile duplicate sightings without pretending perfect identity.

## Decision flow

1. Record the new sighting; verify uncertain detections when feasible.
2. Evaluate survivor urgency, estimated growth, response windows, usable agent,
   energy/return reserve, travel time and fresh received commitments.
3. Estimate the effect of diversion on the original response. Do not count
   unacknowledged, stale or unreachable responders as guaranteed capacity.
4. If permitted, negotiate release/reassignment with bounded timeouts and clear
   commitment versions. The confirmed policy permits diversion only when the
   original owner acknowledges that the remaining fresh team remains sufficient.
5. Otherwise retain the incident as deferred, communicate it, and schedule a
   review. A deferral is neither clearance nor permission to forget it.
6. Reconsider when evidence, responder availability, connectivity, urgency or
   the review deadline changes. Escalate needs beyond estimated swarm capacity.

Priority combines learned evidence with explicit operational constraints.
Current priority: survivor evidence*100, animal*30, severity*12, capped resource
demand urgency, overdue review bonus, age and ETA penalties. These are scenario
weights, not real emergency-response standards. Expired records remain in memory;
idle agents explicitly revisit them with VERIFY commands instead of authorizing
discharge from stale evidence. A quick smaller stop can request release even if
its priority is lower; the owner still requires sufficient fresh acknowledged
capacity and arrival estimates. Release creates a short rebid cooldown.

## Failure cases to verify

- New small incident remains available after the original mission ends.
- Survivor evidence triggers appropriate verification/reprioritization.
- Two drones do not both treat the other's tentative bid as a firm response.
- Link failure cannot silently manufacture permission or fresh resource state.
- Repeated priority changes do not cause endless switching or duplicate work.
- Worsening deferred incidents trigger review; stale reports cannot prove clear.
- ETA and resource estimates remain estimates and expose their assumptions.
