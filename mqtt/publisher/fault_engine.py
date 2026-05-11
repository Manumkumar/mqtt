"""
Fault injection engine.

Manages the lifecycle of simulated faults:
  1. **Schedule** — randomly decide to start a precursor phase.
  2. **Precursor** — slow parameter drift toward warning thresholds
     (labelled MAINTENANCE_ALERT).
  3. **Active** — parameter pushed past failure threshold
     (labelled FAULT).
  4. **Clear** — fault expires, system returns to normal.
"""

import time
import random

from publisher.config import (
    FAULT_TYPES,
    FAULT_DURATIONS,
    PRECURSOR_RANGE,
    FAULT_TRIGGER_PROB,
)


class FaultEngine:
    """Stateful fault-injection controller."""

    def __init__(self):
        # Scheduled (precursor phase)
        self.scheduled_fault: str | None = None
        self.precursor_start: float = 0.0
        self.precursor_end: float = 0.0
        self.precursor_duration: float = 0.0

        # Active fault
        self.active_fault: str | None = None
        self.fault_end: float = 0.0

    # ---- Public API -------------------------------------------------------

    def maybe_schedule_fault(self) -> None:
        """Decide whether to start a precursor leading to a future fault."""
        if self.scheduled_fault is not None or self.active_fault is not None:
            return
        if random.random() >= FAULT_TRIGGER_PROB:
            return
        self.scheduled_fault = random.choice(FAULT_TYPES)
        self.precursor_duration = random.uniform(*PRECURSOR_RANGE)
        self.precursor_start = time.time()
        self.precursor_end = self.precursor_start + self.precursor_duration
        print(
            f"[SCHED] >>> precursor for {self.scheduled_fault} "
            f"({self.precursor_duration:.1f}s drift)"
        )

    def promote_scheduled_to_active(self, stroke_mgr) -> None:
        """When the precursor window ends, promote to an active fault."""
        if self.scheduled_fault is None or time.time() < self.precursor_end:
            return

        name = self.scheduled_fault
        lo, hi = FAULT_DURATIONS[name]
        duration = random.uniform(lo, hi)

        self.active_fault = name
        self.fault_end = time.time() + duration
        self.scheduled_fault = None

        # Some faults force a stroke if not already stroking
        if name in ("OBSTRUCTION", "OVER_CURRENT") and not stroke_mgr.stroking:
            stroke_mgr.force_stroke(
                duration if name == "OBSTRUCTION" else random.uniform(5.0, 7.0)
            )

        print(f"[FAULT] >>> {name} active for {duration:.1f}s")

    def clear_fault_if_expired(self) -> None:
        """Remove the active fault once its duration elapses."""
        if self.active_fault is not None and time.time() >= self.fault_end:
            print(f"[FAULT] <<< {self.active_fault} cleared")
            self.active_fault = None
            self.fault_end = 0.0

    def precursor_progress(self) -> float | None:
        """Return 0..1 progress through the precursor phase, or None."""
        if self.scheduled_fault is None:
            return None
        p = (time.time() - self.precursor_start) / max(self.precursor_duration, 0.001)
        return max(0.0, min(1.0, p))
