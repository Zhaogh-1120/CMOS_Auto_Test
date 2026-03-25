from __future__ import annotations

from instruments.e5052b.client import E5052BClient
from instruments.e5052b.capture import capture_phase_noise_once
from instruments.e5052b.models import E5052BCaptureOptions, E5052BCaptureResult


class Instrument5052B(E5052BClient):
    """Backward-compatible wrapper around the new E5052B module."""

    def capture(self, options: E5052BCaptureOptions, out_dir: str = 'outputs/e5052b', shot_name: str | None = None) -> E5052BCaptureResult:
        return capture_phase_noise_once(self, options=options, out_dir=out_dir, shot_name=shot_name)
