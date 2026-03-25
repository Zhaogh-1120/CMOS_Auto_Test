# Migration Guide

This package has been restructured for maintainability while preserving the original working files.

Recommended long-term direction:
- put common reusable logic under `driver/`, `protocol/`, `core/`
- put chip- or project-specific changes under `config/active/` or a new `config/<project_name>/`
- put experiment scripts under `scripts/basic/`, `scripts/loops/`, or `scripts/experiments/`
