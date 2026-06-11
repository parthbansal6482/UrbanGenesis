"""
analytics/grader.py

Converts ABI timeseries into risk verdicts for Satyukt's clients:
- Insurance companies: premium repricing triggers
- MRV carbon credit: encroachment flags for verification
- Sat4Risk: flood and drought risk amplification scores
"""

from typing import List, Dict

GRADE_THRESHOLDS = [
    (2.0, "A", "Healthy Buffer",
     "Cropland well-protected. Strong agricultural buffer intact. No MRV flags."),
    (1.0, "B", "Moderate Risk",
     "Buffer shrinking but stable. Recommend annual satellite monitoring."),
    (0.5, "C", "Elevated Risk",
     "Urban boundary within encroachment range of active cropland. "
     "Flag for Sat4Risk flood score review."),
    (0.3, "D", "High Risk",
     "Active cropland conversion detected. Insurance premium review recommended. "
     "MRV baseline may be compromised."),
    (0.0, "F", "Critical — Encroachment Alert",
     "Severe urban encroachment. Cropland loss quantified. "
     "Immediate Sat4Risk repricing and MRV audit required."),
]


def assign_grade(abi: float) -> Dict[str, str]:
    """
    Assign a risk grade A–F based on ABI value.

    Args:
        abi: Agricultural Buffer Index (non-negative float, may be inf)

    Returns:
        dict with keys: grade, label, description
    """
    for threshold, grade, label, description in GRADE_THRESHOLDS:
        if abi >= threshold:
            return {"grade": grade, "label": label, "description": description}
    return {
        "grade": "F",
        "label": GRADE_THRESHOLDS[-1][2],
        "description": GRADE_THRESHOLDS[-1][3],
    }


def detect_encroachment_alert(
    timeseries: List[Dict],
    window_years: int = 5,
    drop_threshold: float = 0.20,
) -> bool:
    """
    Returns True if ABI drops by more than drop_threshold
    within any window_years span in the timeseries.

    Args:
        timeseries: list of yearly ABI records, each with 'year' and 'abi' keys
        window_years: maximum span to look for a drop (default: 5 years)
        drop_threshold: fractional drop required to trigger alert (default: 0.20 = 20%)

    Returns:
        bool — True if encroachment alert should be raised
    """
    years = [r["year"] for r in timeseries]
    abis = [r["abi"] for r in timeseries]

    for i, (y_start, abi_start) in enumerate(zip(years, abis)):
        for j, (y_end, abi_end) in enumerate(zip(years, abis)):
            if j <= i:
                continue
            if (y_end - y_start) <= window_years and abi_start > 0:
                pct_drop = (abi_start - abi_end) / abi_start
                if pct_drop >= drop_threshold:
                    return True
    return False


def generate_verdict(
    timeseries: List[Dict],
    zone_name: str,
    cropland_loss_ha: float = 0.0,
) -> Dict:
    """
    Generate a complete risk verdict for a farmland zone.

    Args:
        timeseries: list of yearly ABI records (must be non-empty)
        zone_name: display name for the zone (e.g. "Nashik North Agricultural Zone")
        cropland_loss_ha: total cropland lost in hectares (default: 0.0)

    Returns:
        dict with grade, ABI, summary text, and all supporting metrics
    """
    latest = timeseries[-1]
    abi_latest = latest["abi"]
    first = timeseries[0]
    grade_info = assign_grade(abi_latest)
    alert = detect_encroachment_alert(timeseries)

    overall_change_pct = (
        (abi_latest - first["abi"]) / first["abi"] * 100
        if first["abi"] > 0 else 0.0
    )

    return {
        "zone": zone_name,
        "latest_year": latest["year"],
        "abi": abi_latest,
        "grade": grade_info["grade"],
        "label": grade_info["label"],
        "description": grade_info["description"],
        "overall_abi_change_pct": round(overall_change_pct, 1),
        "cropland_loss_ha": cropland_loss_ha,
        "encroachment_alert": alert,
        "timeseries": timeseries,
        "summary": (
            f"{zone_name} — ABI: {abi_latest:.2f} "
            f"({overall_change_pct:+.1f}% since {first['year']}). "
            f"Cropland lost: {cropland_loss_ha:.1f} ha. "
            f"Grade: {grade_info['grade']} — {grade_info['label']}. "
            + ("⚠️ Encroachment Alert Active."
               if alert else "No active encroachment alert.")
        ),
    }
