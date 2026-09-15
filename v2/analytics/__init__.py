"""Analytics and derived competency calculations for v2.

The package intentionally exposes only native v2 analytics.  Keeping the
legacy helper name ``build_heatmap_matrix`` available here preserves the
existing page contract while avoiding the root-level ``analytics.py`` module.
"""

from .competency import build_heatmap_matrix

__all__ = ["build_heatmap_matrix"]
