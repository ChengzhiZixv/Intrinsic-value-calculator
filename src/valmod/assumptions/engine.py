# =============================================================================
# Layer 4 - Assumptions Engine (engine.py)
# =============================================================================
# Responsibility: generate default valuation assumptions; support user overrides;
# record assumption sources.
# Defaults: r=10%, g=2.5%, explicit period=5 years, growth=historical CAGR or 5%.
#
# Adjustable (via config/analyst_overrides.yaml or overrides parameter):
# - discount_rate:       discount rate [ANALYST_REQUIRED]
# - perpetual_growth:    perpetual growth [ANALYST_REQUIRED]
# - explicit_years:      number of explicit forecast years
# - explicit_growth_rate: explicit period growth rate [ANALYST_REQUIRED]
# - CAGR cap/floor (CAGR_CAP, CAGR_FLOOR) to prevent extreme values
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, Assumptions

# [Adjustable] Historical CAGR cap to prevent extreme high-growth assumptions
CAGR_CAP = 0.15
# [Adjustable] Historical CAGR floor for declining companies
CAGR_FLOOR = -0.10
# [Adjustable] Default growth rate when CAGR cannot be computed
DEFAULT_GROWTH = 0.05


def _compute_revenue_cagr(norm: NormalizedFinancials) -> Optional[float]:
    """
    Compute revenue CAGR. Currently only one year of revenue is available;
    multi-year CAGR cannot be computed. Extend here if a historical series
    becomes available.
    """
    return None


def _compute_fcf_cagr(norm: NormalizedFinancials) -> Optional[float]:
    """Compute FCF CAGR. Same limitation as above; single-year data is insufficient."""
    return None


def build_assumptions(norm: NormalizedFinancials, overrides: Optional[dict] = None) -> Assumptions:
    """
    Generate valuation assumptions.
    Input:  NormalizedFinancials, overrides (optional; overrides defaults)
    Output: Assumptions + assumption_log
    """
    overrides = overrides or {}
    log = []

    # ----- Explicit period growth rate: prefer historical CAGR, else default 5% -----
    cagr = _compute_revenue_cagr(norm) or _compute_fcf_cagr(norm)
    if cagr is not None:
        cagr = max(CAGR_FLOOR, min(CAGR_CAP, cagr))
        explicit_growth = cagr
        log.append(f"Explicit growth = historical CAGR {cagr:.2%} (source: computed)")
    else:
        explicit_growth = overrides.get("explicit_growth_rate", DEFAULT_GROWTH)
        log.append(f"Explicit growth = default {explicit_growth:.2%} (source: conservative default; no historical CAGR available)")

    discount_rate = overrides.get("discount_rate", 0.10)
    perpetual_growth = overrides.get("perpetual_growth", 0.025)
    explicit_years = overrides.get("explicit_years", 5)

    log.append(f"Discount rate = {discount_rate:.2%} (source: {'user override' if 'discount_rate' in overrides else 'default'})")
    log.append(f"Perpetual growth = {perpetual_growth:.2%} (source: {'user override' if 'perpetual_growth' in overrides else 'default'})")
    log.append(f"Explicit years = {explicit_years} (source: {'user override' if 'explicit_years' in overrides else 'default'})")

    return Assumptions(
        discount_rate=discount_rate,
        perpetual_growth=perpetual_growth,
        explicit_years=explicit_years,
        explicit_growth_rate=explicit_growth,
        assumption_log=log,
    )
