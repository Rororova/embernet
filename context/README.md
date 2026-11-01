# EMBERNET â€” agent context

Read `CURRENT_HANDOFF.md`, this index and `STATUS.md` before working. These documents describe the
rebuild; older root-level Ember documents describe superseded prototypes.

| Document | Purpose |
| --- | --- |
| [SWARM_OBJECTIVE_RECOVERY.md](SWARM_OBJECTIVE_RECOVERY.md) | Latest user correction: objective drift, missing visible mission loop and recovery acceptance |
| [CURRENT_HANDOFF.md](CURRENT_HANDOFF.md) | Current stopped checkpoint, exact failures and next actions |
| [ARCHITECTURAL_RUN.md](ARCHITECTURAL_RUN.md) | Authored NVIDIA scene, actual RTX PRO runs, transport fixes and acceptance evidence |
| [STATUS.md](STATUS.md) | Confirmed choices, open questions, implementation status |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Proposed boundaries, data ownership, integration direction |
| [INCIDENT_MEMORY.md](INCIDENT_MEMORY.md) | Deferred incidents, priorities, resource commitments |
| [RUNBOOK.md](RUNBOOK.md) | Installation, launch, replay and recovery |
| [TRAINING.md](TRAINING.md) | Models, demonstrations, PPO, checkpoints and compute |
| [VERIFICATION.md](VERIFICATION.md) | Executed checks, results and limits |
| [LOGS.md](LOGS.md) | Downloaded log inventory and export commands |
| [REAL_PERCEPTION.md](REAL_PERCEPTION.md) | Implemented pretrained RGB/radiometric review, data provenance and results |
| [PX4_CLOUD.md](PX4_CLOUD.md) | PX4 SITL/PhysX conversion, one shared cloud session, access, budgets and logs |
| [ISAAC_SIM.md](ISAAC_SIM.md) | Cloud RTX setup, physics/sensor contracts, assets and executed runtime results |
| [VISUAL_SIMULATION.md](VISUAL_SIMULATION.md) | Shared geometry and live scene semantics |
| [REAL_DATA_PERCEPTION_HANDOFF.md](REAL_DATA_PERCEPTION_HANDOFF.md) | User's real-data correction, FLAME 3 audit and benchmark direction |

Keep documentation proportional: explain contracts, decisions, evidence, and
limitations rather than narrating every edit. Update status when capabilities
change. Distinguish proposed, implemented, and verified features explicitly.

User-provided technical reference:
`C:/Users/Nikhi/Downloads/Swarm_AI_Tech_Stack_Brief.md`.
Treat it as conceptual direction, not proof that integrations are implemented.
