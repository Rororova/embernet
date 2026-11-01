"""Opt-in ordinary POSIX scheduling for SITL in gVisor; never changes flight logic."""

from pathlib import Path

root = Path("/opt/PX4-Autopilot")
tasks = root / "platforms/posix/src/px4/common/tasks.cpp"
text = tasks.read_text()
needle = "rv = pthread_attr_setschedpolicy(&attr, scheduler);"
assert text.count(needle) == 1
text = text.replace(
    needle,
    """// EMBERNET: gVisor provides ordinary Linux scheduling, not SCHED_FIFO.
    // This opt-in path is for the SITL executable only. Flight checks remain intact.
    if (getenv("EMBERNET_SITL_NON_RT")) { scheduler = SCHED_OTHER; priority = 0; }
    """
    + needle,
)
tasks.write_text(text)
queue = root / "platforms/common/px4_work_queue/WorkQueueManager.cpp"
text = queue.read_text()
text = "#include <cstdlib>\n" + text
needle = "pthread_attr_setschedpolicy(&attr, SCHED_FIFO)"
assert text.count(needle) == 1
text = text.replace(
    needle, 'pthread_attr_setschedpolicy(&attr, getenv("EMBERNET_SITL_NON_RT") ? SCHED_OTHER : SCHED_FIFO)'
)
needle = "param.sched_priority = sched_priority;"
assert text.count(needle) == 1
text = text.replace(needle, 'param.sched_priority = getenv("EMBERNET_SITL_NON_RT") ? 0 : sched_priority;')
queue.write_text(text)
print("Installed opt-in SITL scheduling compatibility; controller/arming/failsafe sources unchanged.")
