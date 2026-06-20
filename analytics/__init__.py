"""
analytics — UrbanGenesis farmland analytics package.

Public API:
    compute_abi            — Compute Agricultural Buffer Index from a mask array
    compute_abi_timeseries — Compute ABI for each year in a dict of mask paths
    compute_cropland_loss_ha — Hectares of cropland lost between two masks
    calculate_encroachment_stats  — Pixel-level encroachment stats (ha)
    generate_encroachment_heatmap — RGB heatmap of encroachment transitions
    assign_grade           — Convert ABI float to A-F risk grade dict
    detect_encroachment_alert — Detect rapid ABI drop in timeseries
    generate_verdict       — Full risk verdict for a farmland zone
    detect_urban_expansion — Transition matrix-based urban expansion stats
"""

from analytics.abi import (
    compute_abi,
    compute_abi_from_file,
    compute_abi_timeseries,
    compute_cropland_loss_ha,
)
from analytics.encroachment import (
    calculate_encroachment_stats,
    generate_encroachment_heatmap,
)
from analytics.grader import (
    assign_grade,
    detect_encroachment_alert,
    generate_verdict,
)
from analytics.change_detection import (
    detect_urban_expansion,
    compute_transition_matrix,
)

__all__ = [
    "compute_abi",
    "compute_abi_from_file",
    "compute_abi_timeseries",
    "compute_cropland_loss_ha",
    "calculate_encroachment_stats",
    "generate_encroachment_heatmap",
    "assign_grade",
    "detect_encroachment_alert",
    "generate_verdict",
    "detect_urban_expansion",
    "compute_transition_matrix",
]
