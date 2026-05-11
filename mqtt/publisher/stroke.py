"""
Stroke state machine.

Manages the point-machine stroke lifecycle:
  - idle → stroking (random trigger or forced by fault engine)
  - stroking → complete (position updates to target)
  - motor-current profile generation during stroke
"""

import time
import random


class StrokeManager:
    """Tracks position, stroke state, and generates motor-current profiles."""

    def __init__(self, initial_position: str = "N"):
        self.position: str = initial_position
        self.stroking: bool = False
        self.stroke_target: str | None = None
        self.stroke_start: float = 0.0
        self.stroke_duration: float = 0.0

    # ---- Public API -------------------------------------------------------

    def maybe_start_stroke(self) -> None:
        """Randomly trigger a normal stroke (~1 % chance per tick)."""
        if self.stroking:
            return
        if random.random() < 0.01:
            self._begin_stroke(random.uniform(5.0, 7.0))

    def force_stroke(self, duration: float) -> None:
        """Force a stroke (called by the fault engine for obstruction / over-current)."""
        if not self.stroking:
            self._begin_stroke(duration)

    def update(self, active_fault: str | None) -> tuple[float, float]:
        """Advance the stroke state machine.

        Returns
        -------
        ipt_active : float
            Motor current for the currently-stroking direction (0 if idle).
        tpt_value : float
            Elapsed stroke time (0 if idle).
        """
        if not self.stroking:
            return 0.0, 0.0

        elapsed = time.time() - self.stroke_start

        if elapsed >= self.stroke_duration:
            self.position = self.stroke_target
            self.stroking = False
            self.stroke_target = None
            return 0.0, 0.0

        over_current = active_fault == "OVER_CURRENT"
        if active_fault == "OBSTRUCTION":
            ipt = 5.0 + random.uniform(-0.4, 0.4)
        else:
            ipt = self._current_profile(elapsed / self.stroke_duration, over_current)

        return ipt, elapsed

    # ---- Internals --------------------------------------------------------

    def _begin_stroke(self, duration: float) -> None:
        self.stroking = True
        self.stroke_target = "R" if self.position == "N" else "N"
        self.stroke_start = time.time()
        self.stroke_duration = duration

    @staticmethod
    def _current_profile(t_norm: float, over_current: bool = False) -> float:
        """Stroke motor-current waveform (normalised time 0..1)."""
        scale = random.uniform(2.2, 2.8) if over_current else 1.0
        if t_norm < 0.06:
            return (9.5 + random.uniform(-0.4, 0.4)) * scale
        if t_norm < 0.85:
            return (4.5 + random.uniform(-0.3, 0.3)) * scale
        if t_norm < 1.0:
            tail = 4.5 * (1 - (t_norm - 0.85) / 0.15)
            return max(0.0, tail) * scale + random.uniform(-0.2, 0.2)
        return 0.0
