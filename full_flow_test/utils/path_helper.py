from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_run_dir(base_dir: str | Path, prefix: str = 'run') -> Path:
    base = ensure_dir(base_dir)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = base / f'{prefix}_{ts}'
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def ensure_output_tree(run_dir: str | Path) -> dict[str, Path]:
    run_dir = ensure_dir(run_dir)
    dirs = {
        'run': run_dir,
        'summary': run_dir / 'summary',
        'traces': run_dir / 'traces',
        'screenshots': run_dir / 'screenshots',
        'merged': run_dir / 'merged',
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs
