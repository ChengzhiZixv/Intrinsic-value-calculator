# =============================================================================
# Layer 3 - Classification and Model Selection (selector.py)
# =============================================================================
# Responsibility: decide which valuation models to enable based on data
# availability, and recommend the preferred model based on sector convention.
# Rules: EBITDA available → EV/EBITDA; Revenue available → EV/Sales.
# Recommendation logic: maps yfinance sector field to the most common
# valuation methodology for that sector.
#
# Adjustable:
# - _SECTOR_RECOMMEND: sector → recommended model mapping table
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, SelectionResult

# Sector → recommended model mapping (based on industry valuation conventions)
# Keys match yfinance info["sector"] values
_SECTOR_RECOMMEND: dict = {
    "Technology":             ("damodaran_pe", "Tech sector is EPS-growth driven; Damodaran PE regression best fits industry convention"),
    "Communication Services": ("damodaran_pe", "Media-tech is EPS-growth driven; Damodaran PE regression best fits industry convention"),
    "Healthcare":             ("damodaran_pe", "Healthcare high-growth characteristics; Damodaran PE regression is appropriate"),
    "Consumer Defensive":     ("damodaran_pe", "Consumer defensive companies have stable earnings; PE valuation is the sector norm"),
    "Financial Services":     ("damodaran_pe", "Financial sector predominantly values on PE"),
    "Consumer Cyclical":      ("ev_ebitda",    "Consumer cyclical is volatile; EV/EBITDA removes cyclical D&A for a more stable view"),
    "Industrials":            ("ev_ebitda",    "Capital-intensive industrials; EV/EBITDA strips out D&A to better reflect operating value"),
    "Basic Materials":        ("ev_ebitda",    "Basic materials sector; EV/EBITDA better reflects true operating value"),
    "Energy":                 ("damodaran_iv", "Energy has stable and predictable cash flows; FCFF intrinsic value model is most rigorous"),
    "Utilities":              ("damodaran_iv", "Utilities have regular cash flows; FCFF intrinsic value model is most appropriate"),
    "Real Estate":            ("damodaran_iv", "Real estate is primarily cash-flow valued; FCFF intrinsic value model is most appropriate"),
}


def select_models(norm: NormalizedFinancials, sector: Optional[str] = None) -> SelectionResult:
    """
    Determine which models to enable based on normalized data, and recommend
    the preferred valuation method based on sector.
    Input:  NormalizedFinancials, sector (from yfinance info["sector"])
    Output: SelectionResult (enabled_models, rationale, recommended_model, recommended_reason)
    """
    enabled = []
    rationale_parts = []

    # ----- Rule 1: EBITDA available → enable EV/EBITDA -----
    if norm.ebitda is not None and norm.ebitda > 0:
        enabled.append("ev_ebitda")
        rationale_parts.append("EBITDA available; EV/EBITDA enabled")

    # ----- Rule 2: Revenue available → enable EV/Sales -----
    if norm.revenue is not None and norm.revenue > 0:
        enabled.append("ev_sales")
        rationale_parts.append("Revenue available; EV/Sales enabled")

    enabled = list(dict.fromkeys(enabled))

    if not enabled:
        rationale_parts.append("Insufficient key data; valuation not possible")

    # ----- Sector-based model recommendation -----
    if sector and sector in _SECTOR_RECOMMEND:
        recommended_model, recommended_reason = _SECTOR_RECOMMEND[sector]
    else:
        # No sector info: prefer damodaran_pe (requires EPS), else ev_ebitda
        if norm.net_income is not None:
            recommended_model = "damodaran_pe"
            recommended_reason = "Sector not recognized; defaulting to Damodaran PE (requires gEPS input)"
        else:
            recommended_model = "ev_ebitda"
            recommended_reason = "Sector not recognized; falling back to EV/EBITDA"

    return SelectionResult(
        enabled_models=enabled,
        rationale="; ".join(rationale_parts),
        recommended_model=recommended_model,
        recommended_reason=recommended_reason,
    )
