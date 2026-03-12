"""Compatibility export for the canonical dashboard notebook template."""

from bubseek_marimo.notebooks import get_seed_notebook_content

DASHBOARD_TEMPLATE = get_seed_notebook_content("dashboard.py")

__all__ = ["DASHBOARD_TEMPLATE"]
