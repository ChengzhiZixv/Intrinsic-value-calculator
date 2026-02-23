# =============================================================================
# Layer 5 - Damodaran Intrinsic Value Model (damodaran_iv.py)
# =============================================================================
# Responsibility: automatically select and run one of three Damodaran intrinsic
# value models based on the company's financial characteristics:
#   FCFF (Free Cash Flow to Firm)
#   FCFE (Free Cash Flow to Equity)
#   DDM  (Dividend Discount Model)
#
# Selection logic (based on Damodaran's teaching framework):
#   DDM : payout ratio > 70% AND debt/market cap < 50%  ← mature cash cow (e.g. Coca-Cola)
#   FCFF: debt/market cap > 80% OR net income ≤ 0       ← high-leverage / loss-making
#   FCFE: all other cases                                ← stable leverage with positive earnings
#
# Key parameters (filled by user in the sidebar, passed via overrides):
#   rf              - risk-free rate (10-year US Treasury yield)
#   erp             - equity risk premium (Damodaran monthly update, ~4.2–4.5% for US)
#   default_spread  - default spread (based on company credit rating, e.g. BBB ≈ 1.5–2.0%)
#   sector_beta_unlevered - sector unlevered beta (from damodaran.com)
#   tax_rate        - marginal tax rate
#   g_high_iv       - high-growth phase growth rate
#   n_high_iv       - number of high-growth years (5 for mature, 10 for high-growth)
#   g_stable_iv     - perpetual growth rate (must be ≤ risk-free rate Rf, typically 2–3%)
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, RawData


# ── Model selection ───────────────────────────────────────────────────────────

def select_damodaran_model(raw: RawData) -> tuple:
    """
    Select the most appropriate Damodaran intrinsic value model based on
    the company's financial characteristics.
    Returns: (model_name, reason_str)
      model_name ∈ {"fcff", "fcfe", "ddm"}
    """
    net_income = raw.net_income or 0
    total_debt = raw.total_debt or 0
    market_cap = raw.market_cap or 1
    payout_ratio = raw.payout_ratio or 0
    D_ratio = total_debt / market_cap if market_cap > 0 else 0

    if payout_ratio > 0.7 and D_ratio < 0.5:
        return (
            "ddm",
            f"Payout ratio {payout_ratio:.1%} > 70% and debt/market cap {D_ratio:.1%} < 50%; "
            "matches mature cash cow profile — DDM (Dividend Discount Model) is most appropriate",
        )
    elif D_ratio > 0.8 or net_income <= 0:
        reason = "Net income negative or zero" if net_income <= 0 else f"Debt/market cap {D_ratio:.1%} > 80%"
        return (
            "fcff",
            f"{reason}; FCFF (Free Cash Flow to Firm) is more robust for high-leverage / loss-making companies",
        )
    else:
        return (
            "fcfe",
            f"Stable leverage (debt/market cap {D_ratio:.1%}) with positive net income; "
            "FCFE (Free Cash Flow to Equity) directly measures shareholder returns",
        )


# ── Shared parameter extraction ───────────────────────────────────────────────

def _beta_and_cost_of_equity(raw: RawData, params: dict) -> tuple:
    """
    Returns (beta_levered, re, error_str_or_None)
    re = Rf + β_levered × ERP
    β_levered = β_unlevered × (1 + (1 - t) × D/E)
    """
    Rf = params.get("rf", 0.045)
    ERP = params.get("erp", 0.045)
    t = params.get("tax_rate", 0.25)

    total_debt = raw.total_debt or 0
    market_cap = raw.market_cap or 0
    if market_cap <= 0:
        return (None, None, "Market cap unavailable; cannot compute beta")

    D_E = total_debt / market_cap
    # sector_beta_unlevered may be None (user left 0 → overrides passes None)
    # Fall back to yfinance regression beta (already levered); final fallback is 1.0
    sector_beta_unlevered = params.get("sector_beta_unlevered")
    if sector_beta_unlevered is not None:
        beta_levered = sector_beta_unlevered * (1 + (1 - t) * D_E)
    elif raw.beta is not None:
        beta_levered = raw.beta  # yfinance regression beta is already levered
    else:
        beta_levered = 1.0  # final fallback

    re = Rf + beta_levered * ERP
    return (beta_levered, re, None)


# ── FCFF model ────────────────────────────────────────────────────────────────

def run_fcff(raw: RawData, params: dict) -> dict:
    """
    FCFF = EBIT×(1-t) - Net CapEx - ΔNon-cash WC
    Discount rate: WACC = re×E/(D+E) + rd×(1-t)×D/(D+E)
    rd = Rf + Default Spread
    Terminal value: TV = FCFF_n × (1+g_stable) / (WACC - g_stable)
    Value per share = (EV - Total Debt + Cash) / Diluted Shares
    """
    Rf = params.get("rf", 0.045)
    default_spread = params.get("default_spread", 0.02)
    t = params.get("tax_rate", 0.25)
    g_high = params.get("g_high_iv", 0.10)
    n_high = int(params.get("n_high_iv", 5))
    g_stable = params.get("g_stable_iv", 0.025)
    g_stable = min(g_stable, Rf)  # enforce g ≤ Rf

    # ── Data validation ──
    ebit = raw.operating_income
    if not ebit or ebit <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": "EBIT unavailable or non-positive; FCFF not applicable"}}

    beta_levered, re, err = _beta_and_cost_of_equity(raw, params)
    if err:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFF", "error": err}}

    total_debt = raw.total_debt or 0
    market_cap = raw.market_cap or 1
    cash = raw.cash or 0
    shares = raw.shares or 0
    if shares <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFF", "error": "Shares unavailable"}}

    # ── WACC ──
    V = market_cap + total_debt
    E_w = market_cap / V
    D_w = total_debt / V
    rd = Rf + default_spread
    wacc = re * E_w + rd * (1 - t) * D_w

    if wacc <= g_stable:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": f"WACC({wacc:.2%}) ≤ g_stable({g_stable:.2%}); terminal value undefined"}}

    # ── FCFF_0 ──
    capex_abs = abs(raw.capex) if raw.capex is not None else 0
    depr = abs(raw.depreciation_amortization) if raw.depreciation_amortization is not None else 0
    net_capex = capex_abs - depr

    delta_wc = 0.0
    if raw.working_capital is not None and raw.working_capital_prior is not None:
        delta_wc = raw.working_capital - raw.working_capital_prior

    fcff_0 = ebit * (1 - t) - net_capex - delta_wc
    if fcff_0 <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": f"FCFF_0={fcff_0/1e9:.2f}B is negative; FCFF not applicable (consider FCFE)"}}

    # ── High-growth phase PV ──
    pv_high = sum(fcff_0 * (1 + g_high) ** i / (1 + wacc) ** i for i in range(1, n_high + 1))

    # ── Terminal value ──
    fcff_n = fcff_0 * (1 + g_high) ** n_high
    tv = fcff_n * (1 + g_stable) / (wacc - g_stable)
    pv_tv = tv / (1 + wacc) ** n_high

    # ── Equity value per share ──
    ev = pv_high + pv_tv
    equity_value = ev - total_debt + cash
    if equity_value <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": "Equity value negative (debt exceeds EV)", "ev": round(ev / 1e9, 2)}}

    value_per_share = equity_value / shares

    return {
        "damodaran_iv": value_per_share,
        "damodaran_iv_details": {
            "model_used": "FCFF",
            "beta_levered": round(beta_levered, 3),
            "re": round(re, 4),
            "rd": round(rd, 4),
            "wacc": round(wacc, 4),
            "fcff_0_B": round(fcff_0 / 1e9, 3),
            "net_capex_B": round(net_capex / 1e9, 3),
            "delta_wc_B": round(delta_wc / 1e9, 3),
            "ev_B": round(ev / 1e9, 2),
            "equity_value_B": round(equity_value / 1e9, 2),
            "terminal_pct": round(pv_tv / ev, 4) if ev > 0 else None,
            "g_stable_used": round(g_stable, 4),
        },
    }


# ── FCFE model ────────────────────────────────────────────────────────────────

def run_fcfe(raw: RawData, params: dict) -> dict:
    """
    FCFE = Net Income + D&A - CapEx - ΔWC + Net Debt Issuance
    Discount rate: re (cost of equity, CAPM)
    Terminal value: TV = FCFE_n × (1+g_stable) / (re - g_stable)
    Value per share = PV(FCFE) / Shares
    """
    Rf = params.get("rf", 0.045)
    t = params.get("tax_rate", 0.25)
    g_high = params.get("g_high_iv", 0.10)
    n_high = int(params.get("n_high_iv", 5))
    g_stable = params.get("g_stable_iv", 0.025)
    g_stable = min(g_stable, Rf)

    net_income = raw.net_income
    if not net_income or net_income <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFE", "error": "Net income unavailable or non-positive; FCFE not applicable"}}

    beta_levered, re, err = _beta_and_cost_of_equity(raw, params)
    if err:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFE", "error": err}}

    if re <= g_stable:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFE", "error": f"re({re:.2%}) ≤ g_stable({g_stable:.2%})"}}

    shares = raw.shares or 0
    if shares <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFE", "error": "Shares unavailable"}}

    depr = abs(raw.depreciation_amortization) if raw.depreciation_amortization is not None else 0
    capex_abs = abs(raw.capex) if raw.capex is not None else 0
    delta_wc = 0.0
    if raw.working_capital is not None and raw.working_capital_prior is not None:
        delta_wc = raw.working_capital - raw.working_capital_prior
    net_debt_iss = raw.net_debt_issuance or 0

    fcfe_0 = net_income + depr - capex_abs - delta_wc + net_debt_iss
    if fcfe_0 <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFE", "error": f"FCFE_0={fcfe_0/1e9:.2f}B is negative (consider FCFF)"}}

    pv_high = sum(fcfe_0 * (1 + g_high) ** i / (1 + re) ** i for i in range(1, n_high + 1))
    fcfe_n = fcfe_0 * (1 + g_high) ** n_high
    tv = fcfe_n * (1 + g_stable) / (re - g_stable)
    pv_tv = tv / (1 + re) ** n_high

    equity_value = pv_high + pv_tv
    value_per_share = equity_value / shares

    return {
        "damodaran_iv": value_per_share,
        "damodaran_iv_details": {
            "model_used": "FCFE",
            "beta_levered": round(beta_levered, 3),
            "re": round(re, 4),
            "fcfe_0_B": round(fcfe_0 / 1e9, 3),
            "net_income_B": round(net_income / 1e9, 3),
            "depr_B": round(depr / 1e9, 3),
            "capex_B": round(capex_abs / 1e9, 3),
            "delta_wc_B": round(delta_wc / 1e9, 3),
            "net_debt_iss_B": round(net_debt_iss / 1e9, 3),
            "equity_value_B": round(equity_value / 1e9, 2),
            "terminal_pct": round(pv_tv / equity_value, 4) if equity_value > 0 else None,
            "g_stable_used": round(g_stable, 4),
        },
    }


# ── DDM model ─────────────────────────────────────────────────────────────────

def run_ddm(raw: RawData, params: dict) -> dict:
    """
    DDM: Value per share = PV(DPS high-growth phase) + PV(terminal value)
    Terminal value: TV = DPS_n × (1+g_stable) / (re - g_stable)
    Constraint: g_stable ≤ Rf (risk-free rate)
    DPS source: prefer actual dividends paid / shares; fall back to EPS × payout ratio
    """
    Rf = params.get("rf", 0.045)
    t = params.get("tax_rate", 0.25)
    g_high = params.get("g_high_iv", 0.05)   # DDM high-growth is typically lower
    n_high = int(params.get("n_high_iv", 5))
    g_stable = params.get("g_stable_iv", 0.025)
    g_stable = min(g_stable, Rf)  # enforce: g ≤ Rf

    beta_levered, re, err = _beta_and_cost_of_equity(raw, params)
    if err:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "DDM", "error": err}}

    if re <= g_stable:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "DDM", "error": f"re({re:.2%}) ≤ g_stable({g_stable:.2%})"}}

    shares = raw.shares or 0
    if shares <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "DDM", "error": "Shares unavailable"}}

    # ── DPS ──
    dps = None
    dps_source = ""
    if raw.dividends_paid is not None and shares > 0:
        dps = raw.dividends_paid / shares
        dps_source = "Cash flow statement (actual dividends paid)"
    elif raw.diluted_eps is not None and raw.payout_ratio is not None:
        dps = raw.diluted_eps * raw.payout_ratio
        dps_source = "EPS × payout ratio (estimated)"

    if not dps or dps <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "DDM", "error": "DPS unavailable or zero (company pays no dividends; DDM not applicable)"}}

    pv_high = sum(dps * (1 + g_high) ** i / (1 + re) ** i for i in range(1, n_high + 1))
    dps_n = dps * (1 + g_high) ** n_high
    tv = dps_n * (1 + g_stable) / (re - g_stable)
    pv_tv = tv / (1 + re) ** n_high

    value_per_share = pv_high + pv_tv

    return {
        "damodaran_iv": value_per_share,
        "damodaran_iv_details": {
            "model_used": "DDM",
            "beta_levered": round(beta_levered, 3),
            "re": round(re, 4),
            "dps_0": round(dps, 4),
            "dps_source": dps_source,
            "g_stable_used": round(g_stable, 4),
            "g_stable_constraint": f"g_stable capped at ≤ Rf({Rf:.2%})",
            "terminal_pct": round(pv_tv / value_per_share, 4) if value_per_share > 0 else None,
        },
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def run_damodaran_iv(raw: RawData, params: dict) -> dict:
    """
    Auto-select FCFF/FCFE/DDM and run, returning the intrinsic value estimate.
    Input:  RawData, params (containing rf/erp/default_spread/sector_beta_unlevered, etc.)
    Output: {damodaran_iv, damodaran_iv_details}
      details includes model_used, selection_reason, auto_model, is_manual_override, etc.
    Supports params["iv_model_override"] ∈ {"fcff","fcfe","ddm"} to force a specific sub-model.
    """
    # Always run the auto-selection logic (retain recommendation even when overridden, for UI display)
    auto_model, auto_reason = select_damodaran_model(raw)

    model_override = (params.get("iv_model_override") or "").lower().strip()
    if model_override in ("fcff", "fcfe", "ddm"):
        model_name = model_override
        selection_reason = f"User manually selected {model_name.upper()} (auto-recommendation: {auto_model.upper()})"
        is_manual = True
    else:
        model_name = auto_model
        selection_reason = auto_reason
        is_manual = False

    if model_name == "fcff":
        result = run_fcff(raw, params)
    elif model_name == "fcfe":
        result = run_fcfe(raw, params)
    else:
        result = run_ddm(raw, params)

    # Inject metadata
    if result.get("damodaran_iv_details") is not None:
        result["damodaran_iv_details"]["selection_reason"] = selection_reason
        result["damodaran_iv_details"]["auto_model"] = auto_model
        result["damodaran_iv_details"]["is_manual_override"] = is_manual

    return result
