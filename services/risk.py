"""
Knowledge Risk Detector.

A transparent, explainable scoring heuristic - not a scientific measurement.
Every component is shown to the user alongside the final score so the number
is never a black box.
"""

WEIGHTS = {
    "practitioner_decline": 0.25,
    "youth_participation": 0.20,
    "documentation_gap": 0.20,
    "frequency_decline": 0.15,
    "geographic_concentration": 0.10,
    "low_transmission": 0.10,
}


def _clamp(value, low=0, high=100):
    return max(low, min(high, value))


def compute_risk(practitioners, young_practitioners, documentation_level,
                  frequency_trend, geographic_concentration, transmission_level):
    """documentation_level, frequency_trend, transmission_level: 1-5, 5 = healthiest.
    geographic_concentration: 1-5, 5 = most concentrated (riskiest).
    Returns (score, band, breakdown)."""

    practitioners = max(0, practitioners)
    young_practitioners = max(0, min(young_practitioners, practitioners))

    practitioner_component = _clamp(100 - practitioners * 5)
    youth_ratio = (young_practitioners / practitioners) if practitioners else 0
    youth_component = _clamp((1 - youth_ratio) * 100)
    documentation_component = _clamp((5 - documentation_level) / 4 * 100)
    frequency_component = _clamp((5 - frequency_trend) / 4 * 100)
    geographic_component = _clamp((geographic_concentration - 1) / 4 * 100)
    transmission_component = _clamp((5 - transmission_level) / 4 * 100)

    breakdown = {
        "practitioner_decline": round(practitioner_component, 1),
        "youth_participation": round(youth_component, 1),
        "documentation_gap": round(documentation_component, 1),
        "frequency_decline": round(frequency_component, 1),
        "geographic_concentration": round(geographic_component, 1),
        "low_transmission": round(transmission_component, 1),
    }

    score = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)
    score = round(_clamp(score), 1)

    if score >= 81:
        band = "Critical"
    elif score >= 61:
        band = "High"
    elif score >= 31:
        band = "Medium"
    else:
        band = "Low"

    return score, band, breakdown


RECOMMENDATIONS = {
    "Critical": [
        "Prioritize recording remaining practitioners this quarter",
        "Connect a young learner with a practitioner for hands-on transmission",
        "Organize a documentation workshop with a Community Steward",
    ],
    "High": [
        "Schedule a recording session with remaining practitioners",
        "Create simple educational material from existing recordings",
        "Support a local workshop or demonstration event",
    ],
    "Medium": [
        "Encourage more practitioners to record their knowledge",
        "Track youth participation over the next cycle",
    ],
    "Low": [
        "Continue routine documentation as capacity allows",
    ],
}
