# =============================================================================
# Layer 8 - Intelligent Alerts and Context (context.py)
# =============================================================================
# Responsibility: generate tiered alerts (Critical/Warning), valuation
# uncertainty warnings, and aggressive accounting detection.
#
# Adjustable (constants below):
# - TERMINAL_PCT_WARN:      terminal value share alert threshold
# - DIVERGENCE_WARN:        model divergence alert threshold
# - DA_REVENUE_THRESHOLD:   D&A / revenue ratio anomaly threshold
# - FCF_NI_RATIO_FLOOR:     FCF / net income long-term low threshold
# =============================================================================

from typing import Optional

from src.valmod.types import DataQualityReport, ModelOutputs, RawData, NormalizedFinancials, AlertItem

TERMINAL_PCT_WARN = 0.70
DIVERGENCE_WARN = 0.30
DA_REVENUE_THRESHOLD = 0.15
FCF_NI_RATIO_FLOOR = 0.5


def build_warnings(
    quality: DataQualityReport,
    models: ModelOutputs,
    terminal_pct: Optional[float],
    raw: Optional[RawData] = None,
    norm: Optional[NormalizedFinancials] = None,
) -> list:
    """
    Generate a tiered alert list.
    Input:  quality, models, terminal_pct, raw, norm
    Output: list of AlertItem
    """
    alerts = []

    for c in quality.critical:
        alerts.append(AlertItem(level="critical", message=c, reason="Data quality", affected_models=[], suggestion="Verify data source"))

    for w in quality.warnings:
        alerts.append(AlertItem(level="warning", message=w, reason="Data quality", affected_models=[], suggestion=""))

    if terminal_pct is not None and terminal_pct > TERMINAL_PCT_WARN:
        alerts.append(AlertItem(
            level="warning",
            message=f"Terminal value accounts for {terminal_pct:.1%}, exceeding {TERMINAL_PCT_WARN:.0%}",
            reason="Valuation highly sensitive to long-term assumptions",
            affected_models=["damodaran_iv"],
            suggestion="Manually review perpetual growth rate and discount rate",
        ))

    if models.model_warnings:
        for mw in models.model_warnings:
            alerts.append(AlertItem(level="warning", message=mw, reason="Model output", affected_models=[], suggestion=""))

    if raw is not None and norm is not None:
        if raw.depreciation_amortization is not None and raw.revenue is not None and raw.revenue > 0:
            da_ratio = raw.depreciation_amortization / raw.revenue
            if da_ratio > DA_REVENUE_THRESHOLD:
                alerts.append(AlertItem(
                    level="warning",
                    message=f"D&A / Revenue ratio {da_ratio:.1%} is elevated",
                    reason="PE-based valuation may be distorted",
                    affected_models=["damodaran_pe"],
                    suggestion="Review maintenance CapEx and asset disposals",
                ))

        if norm.fcf is not None and norm.net_income is not None and norm.net_income > 0:
            ratio = norm.fcf / norm.net_income
            if ratio < FCF_NI_RATIO_FLOOR:
                alerts.append(AlertItem(
                    level="warning",
                    message=f"FCF / Net Income ratio {ratio:.2f} is low",
                    reason="Earnings and cash flow are diverging",
                    affected_models=["damodaran_iv"],
                    suggestion="Review operating cash flow quality",
                ))

    return alerts
