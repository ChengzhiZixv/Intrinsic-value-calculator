# =============================================================================
# Layer 5 - Relative Valuation (multiples.py)
# =============================================================================
# Responsibility: derive EV/EBITDA and EV/Sales multiples from fundamentals,
# rather than anchoring to subjective industry benchmarks.
#
# Core philosophy (Damodaran):
#   Multiples are essentially compressed DCF — any reasonable multiple can be
#   derived from fundamentals, rather than relying on a subjective number
#   like "12x industry average".
#
# EV/EBITDA derivation:
#   EV/EBIT = (1-t)(1-RR) / (WACC-g)          ← variant of the FCFF Gordon Growth Model
#   Note: EBIT ≈ EBITDA used as an approximation (ignoring D&A difference)
#
# EV/Sales derivation:
#   EV/Sales = After-tax EBIT margin × (1-RR) × (1+g) / (WACC-g)
#
# Where RR (Reinvestment Rate) = Net CapEx / NOPAT = (CapEx - D&A) / (EBIT × (1-t))
# WACC is preferably taken from the Damodaran IV model result (passed via overrides["_computed_wacc"])
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, RawData


def run_multiples(
    norm: NormalizedFinancials,
    raw: RawData,
    overrides: Optional[dict] = None,
) -> dict:
    """
    Fundamentals-driven relative valuation (EV/EBITDA, EV/Sales).
    Multiples are derived from WACC, g, reinvestment rate, and after-tax margin
    rather than hard-coded.

    Key overrides fields:
      _computed_wacc  - preferred: WACC/re computed by the Damodaran IV model
      rf, erp, default_spread, beta - fallback: used to compute re/WACC independently
      g_stable_iv     - perpetual growth rate
      tax_rate        - marginal tax rate
    """
    overrides = overrides or {}
    tax_rate = overrides.get("tax_rate", 0.25)
    g = overrides.get("g_stable_iv", 0.025)

    # ── 1. Obtain discount rate ────────────────────────────────────────────────
    # Prefer WACC already computed by Damodaran IV (firm-level); fall back to re approximation
    wacc = overrides.get("_computed_wacc")

    if wacc is None and overrides.get("rf") is not None:
        rf = overrides["rf"]
        erp = overrides.get("erp", 0.045)
        beta = raw.beta or 1.0
        re = rf + beta * erp
        if raw.market_cap and raw.total_debt and raw.market_cap > 0:
            rd = rf + overrides.get("default_spread", 0.015)
            d = raw.total_debt or 0
            e = raw.market_cap
            wacc = re * e / (d + e) + rd * (1 - tax_rate) * d / (d + e)
        else:
            wacc = re

    if wacc is None:
        wacc = 0.10  # final default fallback

    if wacc <= g:
        g = max(wacc - 0.005, 0.005)  # prevent division by zero; adjust g

    # ── 2. Compute reinvestment rate (Net CapEx / NOPAT) ──────────────────────
    capex = abs(raw.capex or 0)
    da = raw.depreciation_amortization or 0
    ebit = raw.operating_income or 0
    nopat = ebit * (1 - tax_rate)
    net_capex = max(capex - da, 0)

    if nopat > 0:
        reinv_rate = net_capex / nopat
        reinv_rate = max(0.0, min(reinv_rate, 0.95))  # cap to reasonable range
    else:
        reinv_rate = 0.30  # conservative 30% assumption when NOPAT is unavailable

    # ── 3. Derive implied EV/EBITDA multiple from fundamentals ────────────────
    # Formula: (1-t)(1-RR) / (WACC-g)
    implied_ev_ebitda_mult = (1 - tax_rate) * (1 - reinv_rate) / (wacc - g)
    implied_ev_ebitda_mult = max(implied_ev_ebitda_mult, 0)

    ev_ebitda_val = None
    if raw.ebitda and raw.ebitda > 0 and norm.shares_diluted and norm.shares_diluted > 0:
        ev_implied = implied_ev_ebitda_mult * raw.ebitda
        equity_val = ev_implied - (norm.net_debt or 0)
        ev_ebitda_val = equity_val / norm.shares_diluted if equity_val > 0 else None

    # ── 4. Derive implied EV/Sales multiple from fundamentals ─────────────────
    # Formula: after-tax EBIT margin × (1-RR) × (1+g) / (WACC-g)
    revenue = norm.revenue
    after_tax_margin = None
    implied_ev_sales_mult = 0.0
    ev_sales_val = None

    if revenue and revenue > 0 and ebit:
        after_tax_margin = (ebit * (1 - tax_rate)) / revenue
        implied_ev_sales_mult = after_tax_margin * (1 - reinv_rate) * (1 + g) / (wacc - g)
        implied_ev_sales_mult = max(implied_ev_sales_mult, 0)

        if norm.shares_diluted and norm.shares_diluted > 0:
            ev_implied = implied_ev_sales_mult * revenue
            equity_val = ev_implied - (norm.net_debt or 0)
            ev_sales_val = equity_val / norm.shares_diluted if equity_val > 0 else None

    return {
        "ev_ebitda": ev_ebitda_val,
        "ev_sales": ev_sales_val,
        "details": {
            "implied_ev_ebitda_mult": round(implied_ev_ebitda_mult, 2),
            "implied_ev_sales_mult": round(implied_ev_sales_mult, 2),
            "reinvestment_rate": round(reinv_rate, 4),
            "after_tax_margin": round(after_tax_margin, 4) if after_tax_margin is not None else None,
            "wacc_used": round(wacc, 4),
            "g_used": round(g, 4),
        },
    }


# =============================================================================
# Damodaran PE Regression Model (January 2025)
# Formula: PE = 24.17 - 1.07×Beta + 53.16×gEPS + 1.08×PayoutRatio
# Reference: Aswath Damodaran, January 2025 PE regression
# =============================================================================

# [Adjustable] Regression coefficients (from Damodaran January 2025 data)
_INTERCEPT  = 24.17
_COEF_BETA  = -1.07
_COEF_GEPS  = 53.16
_COEF_PAYOUT = 1.08


def run_damodaran_pe(
    raw: "RawData",
    gEPS: float,
    sector_beta_unlevered: Optional[float] = None,
    tax_rate: float = 0.25,
) -> dict:
    """
    Damodaran PE regression valuation (January 2025 version).
    PE = 24.17 - 1.07×Beta + 53.16×gEPS + 1.08×PayoutRatio
    Target Price = PE × Diluted EPS

    Parameters:
      gEPS                  - expected annual EPS growth rate (decimal, e.g. 0.10 = 10%)
      sector_beta_unlevered - sector unlevered beta (from Damodaran website); uses yfinance beta if None
      tax_rate              - marginal tax rate, default 25%
    """
    # ── 1. Compute beta ────────────────────────────────────────────────────────
    if sector_beta_unlevered is not None and raw.market_cap and raw.market_cap > 0:
        d_e = (raw.total_debt or 0) / raw.market_cap
        beta_used = sector_beta_unlevered * (1 + (1 - tax_rate) * d_e)
        beta_source = "Damodaran bottom-up (sector unlevered beta re-levered)"
    elif raw.beta is not None:
        beta_used = raw.beta
        beta_source = "yfinance regression beta (fallback)"
    else:
        return {"damodaran_pe": None, "damodaran_pe_details": None}

    # ── 2. Payout ratio ───────────────────────────────────────────────────────
    payout = raw.payout_ratio if raw.payout_ratio is not None else 0.0

    # ── 3. Regression formula ─────────────────────────────────────────────────
    pe_implied = _INTERCEPT + _COEF_BETA * beta_used + _COEF_GEPS * gEPS + _COEF_PAYOUT * payout

    if pe_implied <= 0:
        return {"damodaran_pe": None, "damodaran_pe_details": {
            "pe_implied": pe_implied, "beta": beta_used, "gEPS": gEPS,
            "payout_ratio": payout, "note": "Regression PE is negative; model not applicable"
        }}

    # ── 4. Target price = PE × Diluted EPS ───────────────────────────────────
    target_price = None
    if raw.diluted_eps and raw.diluted_eps > 0:
        target_price = pe_implied * raw.diluted_eps

    details = {
        "pe_implied": round(pe_implied, 2),
        "beta_used": round(beta_used, 3),
        "beta_source": beta_source,
        "gEPS": gEPS,
        "payout_ratio": round(payout, 4),
        "diluted_eps": raw.diluted_eps,
        "formula": f"PE = 24.17 - 1.07×{beta_used:.3f} + 53.16×{gEPS:.3f} + 1.08×{payout:.4f} = {pe_implied:.2f}x",
    }

    return {"damodaran_pe": target_price, "damodaran_pe_details": details}
