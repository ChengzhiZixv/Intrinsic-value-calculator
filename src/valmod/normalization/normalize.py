# =============================================================================
# Layer 2 - Normalization Layer (normalize.py)
# =============================================================================
# Responsibility: transform RawData into NormalizedFinancials ready for valuation.
# Handles: FCF = CFO - CapEx, net debt, ratios, shares fallback, CapEx fallback.
# All estimates are recorded in transform_log for review.
#
# Adjustable: no business parameters. If accounting line names change,
# update the mappings here.
# =============================================================================

from typing import Optional

from src.valmod.types import RawData, NormalizedFinancials


def normalize(raw: RawData) -> NormalizedFinancials:
    """
    Normalize raw data.
    Input:  RawData
    Output: NormalizedFinancials (with transform_log recording all computations and estimates)
    """
    log = []

    # ----- Shares: prefer info field; back-calculate from market cap / price if missing -----
    shares_diluted = raw.shares
    if shares_diluted is None and raw.market_cap is not None and raw.current_price is not None and raw.current_price > 0:
        shares_diluted = raw.market_cap / raw.current_price
        log.append("Shares estimated from market cap / price (noted: shares back-calculated)")

    # ----- CapEx fallback: approximate from annual change in net PP&E if missing -----
    capex = raw.capex
    if capex is None and raw.ppe_net is not None and raw.ppe_net_prior is not None:
        capex = -(raw.ppe_net - raw.ppe_net_prior)
        log.append("CapEx approximated from annual change in net PP&E (affected by D&A, disposals, M&A — noted: CapEx estimated)")

    # ----- FCF = CFO - CapEx (when CapEx is negative, FCF = CFO + |CapEx|) -----
    fcf = None
    if raw.cfo is not None:
        if capex is not None:
            fcf = raw.cfo + capex if capex < 0 else raw.cfo - capex
        else:
            log.append("CapEx missing and cannot be estimated; FCF not computable; DCF disabled")
    else:
        log.append("CFO missing; FCF not computable; DCF disabled")

    # ----- Net debt = Total Debt - Cash -----
    net_debt = None
    if raw.total_debt is not None and raw.cash is not None:
        net_debt = raw.total_debt - raw.cash

    # ----- Ratios (computed when data is available) -----
    fcf_margin = None
    if fcf is not None and raw.revenue is not None and raw.revenue > 0:
        fcf_margin = fcf / raw.revenue

    ebitda_margin = None
    if raw.ebitda is not None and raw.revenue is not None and raw.revenue > 0:
        ebitda_margin = raw.ebitda / raw.revenue

    roe = None
    if raw.net_income is not None and raw.market_cap is not None and raw.market_cap > 0:
        roe = raw.net_income / raw.market_cap

    return NormalizedFinancials(
        ticker=raw.ticker,
        fcf=fcf,
        net_debt=net_debt,
        revenue=raw.revenue,
        ebitda=raw.ebitda,
        net_income=raw.net_income,
        fcf_margin=fcf_margin,
        ebitda_margin=ebitda_margin,
        roe=roe,
        shares_diluted=shares_diluted,
        period_type="annual",
        transform_log=log,
    )
