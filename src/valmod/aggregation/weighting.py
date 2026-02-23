# =============================================================================
# Layer 7 - Model Aggregation (weighting.py)
# =============================================================================
# Core logic: uses Damodaran IV (FCFF/FCFE/DDM) as the intrinsic value anchor;
# relative valuation (EV/EBITDA, EV/Sales) and PE regression serve as
# confidence interval cross-checks.
#
# Aggregation rules:
#   1. If Damodaran IV is available → mid = IV; low/high = mid ± 15%
#      Any relative valuation diverging from IV by > IV_DIVERGENCE_THRESHOLD → divergence_alert
#   2. If IV unavailable but Damodaran PE available → mid = PE; range same as above
#   3. Fallback: equal-weight average of all available models
#
# Adjustable:
# - IV_DIVERGENCE_THRESHOLD: alert threshold for relative vs. intrinsic value divergence (default 20%)
# - SPREAD_ALERT_THRESHOLD:  alert if max spread across all models exceeds this (default 30%)
# =============================================================================

from src.valmod.types import ModelOutputs, FinalRange

IV_DIVERGENCE_THRESHOLD = 0.20   # relative valuation diverges from IV by >20% → alert
SPREAD_ALERT_THRESHOLD  = 0.30   # total model spread > 30% of mid → alert


def aggregate(models: ModelOutputs) -> FinalRange:
    """
    IV-anchored aggregation: uses intrinsic value as the mid-point, with
    relative valuation as a confidence interval cross-check.
    Input:  ModelOutputs
    Output: FinalRange
    """
    contributions = {}
    if models.damodaran_iv is not None:
        contributions["damodaran_iv"] = models.damodaran_iv
    if models.damodaran_pe is not None:
        contributions["damodaran_pe"] = models.damodaran_pe
    if models.ev_ebitda is not None:
        contributions["ev_ebitda"] = models.ev_ebitda
    if models.ev_sales is not None:
        contributions["ev_sales"] = models.ev_sales

    values = list(contributions.values())
    if not values:
        return FinalRange(low=0.0, mid=0.0, high=0.0, model_contributions=contributions,
                          weight_explain="No models available", divergence_alert=False)

    # ── Determine mid ─────────────────────────────────────────────────────────
    if models.damodaran_iv is not None:
        mid = models.damodaran_iv
        anchor_name = "Damodaran IV (intrinsic value)"
    elif models.damodaran_pe is not None:
        mid = models.damodaran_pe
        anchor_name = "Damodaran PE (IV model not run)"
    else:
        mid = sum(values) / len(values)
        anchor_name = f"Equal-weight average ({len(values)} models)"

    # ── Divergence check: distance between relative valuation and anchor ──────
    divergence_alert = False
    if mid and mid > 0:
        relative_keys = [k for k in contributions if k not in ("damodaran_iv", "damodaran_pe")]
        for k in relative_keys:
            dev = abs(contributions[k] - mid) / mid
            if dev > IV_DIVERGENCE_THRESHOLD:
                divergence_alert = True
                break
        # Also check total spread across all models
        v_min, v_max = min(values), max(values)
        if (v_max - v_min) / mid > SPREAD_ALERT_THRESHOLD:
            divergence_alert = True

    # Range fixed to ±15% of the best model's value (mid)
    # No longer using cross-model scatter to widen the range, which would make
    # it meaninglessly wide when model assumptions differ substantially.
    if mid > 0:
        low = mid * 0.85
        high = mid * 1.15
    else:
        low = 0.0
        high = 0.0

    weight_explain = f"{anchor_name} anchor | range = ±15% of mid"

    return FinalRange(
        low=low,
        mid=mid,
        high=high,
        model_contributions=contributions,
        weight_explain=weight_explain,
        divergence_alert=divergence_alert,
    )
