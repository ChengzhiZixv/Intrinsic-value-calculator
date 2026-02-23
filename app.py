"""
US Equity Valuation (learning tool). Run: streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="US Equity Valuation", layout="wide")
st.title("US Equity Valuation Tool")

ticker = st.text_input(
    "Ticker Symbol",
    value="",
    max_chars=10,
    placeholder="e.g. AAPL  PLTR  ORCL  MSFT",
)

if not ticker or not ticker.strip():
    st.info("Enter a ticker symbol to start valuation.")
    st.stop()

ticker = ticker.strip().upper()

# ── Sidebar: valuation parameters ────────────────────────────────────────────
with st.sidebar:
    st.header("Valuation Parameters")

    # ── Model 1: PE Regression Valuation ─────────────────────────────────────
    st.markdown("#### Model 1: PE Regression Valuation")
    st.caption("Parameters below are **used exclusively by the PE regression model**. Tax rate is also shared with the intrinsic value model.")

    gEPS_pct = st.number_input(
        "Expected EPS Growth gEPS (%)  ★ Required",
        min_value=-20.0, max_value=100.0, value=10.0, step=0.5,
        format="%.1f",
        help=(
            "Your expected annual EPS growth rate for this company.\n\n"
            "The most influential variable in the PE regression (coefficient 53.16).\n"
            "Typically referenced from sell-side consensus or historical EPS growth, range 5–20%."
        ),
    )

    sector_beta_unlevered = st.number_input(
        "Sector Unlevered Beta  [Optional: leave 0 to use yfinance beta]",
        min_value=0.0, max_value=3.00, value=0.0, step=0.05,
        format="%.2f",
        help=(
            "Sector average unlevered beta from Damodaran's website (updated every January):\n"
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html\n\n"
            "Typical values: Software/Cloud ≈ 1.15, Consumer ≈ 0.80, Financials ≈ 0.40.\n\n"
            "The system re-levers beta using the company D/E ratio automatically.\n"
            "Leave 0: falls back to yfinance regression beta (less accurate, for reference only)."
        ),
    )

    tax_rate_pct = st.number_input(
        "Marginal Tax Rate (%)  [Shared by Model 1 + Model 3]",
        min_value=0.0, max_value=40.0, value=25.0, step=1.0,
        format="%.0f",
        help=(
            "Combined US federal + state tax rate, typically 25%.\n\n"
            "PE regression: used to compute levered beta.\n"
            "Intrinsic value discounting: used to compute NOPAT, WACC, and reinvestment rate."
        ),
    )

    st.markdown("---")
    st.caption("*Model 2 (Relative Valuation) requires no extra parameters — multiples are auto-derived from Model 3 WACC and financial data*")
    st.markdown("---")

    # ── Model 3: Intrinsic Value Discounting (FCFF / FCFE / DDM) ─────────────
    st.markdown("#### Model 3: Intrinsic Value Discounting (FCFF / FCFE / DDM)")
    st.caption(
        "Parameters below are **used exclusively by the intrinsic value discounting model**, "
        "and are also passed to Model 2's EV/EBITDA and EV/Sales multiple derivation."
    )

    rf_pct = st.number_input(
        "Risk-Free Rate Rf (%)  ★ Required",
        min_value=0.5, max_value=10.0, value=4.5, step=0.1,
        format="%.1f",
        help=(
            "Typically the 10-year US Treasury yield (currently ~4–5%).\n\n"
            "Usage: CAPM base return → cost of equity re = Rf + β × ERP.\n"
            "Constraint: perpetual growth rate g_stable must be ≤ Rf."
        ),
    )

    erp_pct = st.number_input(
        "Equity Risk Premium ERP (%)  ★ Required",
        min_value=1.0, max_value=10.0, value=4.5, step=0.1,
        format="%.1f",
        help=(
            "Expected excess return of equities over risk-free assets; ~4.2–4.5% for US stocks.\n\n"
            "Source: Damodaran's website (updated monthly):\n"
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/implprem/ERPbymonth.xlsx\n\n"
            "Usage: re = Rf + β × ERP → discounts equity cash flows (FCFE/DDM) and WACC equity component (FCFF)."
        ),
    )

    default_spread_pct = st.number_input(
        "Default Spread (%)  [FCFF only]",
        min_value=0.0, max_value=10.0, value=1.5, step=0.1,
        format="%.1f",
        help=(
            "Look up based on the company's credit rating.\n\n"
            "Usage: pre-tax cost of debt rd = Rf + Default Spread → computes WACC.\n"
            "BBB ≈ 1.5–2.0%, A ≈ 0.8–1.2%, BB ≈ 2.5–3.5%.\n"
            "Only used when the system selects the FCFF model; FCFE / DDM do not use this."
        ),
    )

    g_high_iv_pct = st.number_input(
        "High Growth Rate (%)  ★ Required",
        min_value=0.0, max_value=40.0, value=10.0, step=0.5,
        format="%.1f",
        help=(
            "Annual growth rate during the high-growth phase (FCF growth for FCFF/FCFE, DPS growth for DDM).\n\n"
            "Reference analyst consensus or historical growth; typically 5–20%."
        ),
    )

    n_high_iv = st.number_input(
        "High Growth Period (years)  ★ Required",
        min_value=1, max_value=15, value=5, step=1,
        format="%d",
        help=(
            "Number of years in the high-growth phase, after which the company enters perpetual growth.\n\n"
            "5 years for mature companies; 7–10 years for high-growth companies."
        ),
    )

    g_stable_iv_pct = st.number_input(
        "Perpetual Growth Rate g_stable (%)  ★ Required",
        min_value=0.0, max_value=5.0, value=2.5, step=0.1,
        format="%.1f",
        help=(
            "Perpetual growth rate after the high-growth phase ends (approximately nominal GDP growth).\n\n"
            "Hard constraint: system enforces g_stable ≤ Rf to prevent terminal value explosion.\n"
            "Typically 2–3%; should not exceed Rf."
        ),
    )

# ── Session state key suffix (isolated per ticker, prevents stale state) ─────
_sfx = f"__{ticker}"


def _ss(key, default=None):
    """Read the session state value bound to the current ticker."""
    return st.session_state.get(key + _sfx, default)


# ── Aggregate overrides (sidebar + inline fill-in data) ──────────────────────
overrides = {
    "gEPS": gEPS_pct / 100,
    "sector_beta_unlevered": sector_beta_unlevered if sector_beta_unlevered > 0 else None,
    "tax_rate": tax_rate_pct / 100,
    "rf": rf_pct / 100,
    "erp": erp_pct / 100,
    "default_spread": default_spread_pct / 100,
    "g_high_iv": g_high_iv_pct / 100,
    "n_high_iv": int(n_high_iv),
    "g_stable_iv": g_stable_iv_pct / 100,
}

# Inline financials override (read from card input widgets on previous render)
_raw_override_map = {
    # key_suffix → overrides_key
    "raw_diluted_eps":          "raw_diluted_eps",
    "raw_payout_pct":           None,   # special handling (% → decimal)
    "raw_operating_income_b":   "raw_operating_income_b",
    "raw_capex_b":              "raw_capex_b",
    "raw_da_b":                 "raw_da_b",
    "raw_net_income_b":         "raw_net_income_b",
    "raw_total_debt_b":         "raw_total_debt_b",
    "raw_cash_b":               "raw_cash_b",
    "raw_shares_b":             "raw_shares_b",
    "raw_ebitda_b":             "raw_ebitda_b",
    "raw_revenue_b":            "raw_revenue_b",
    "raw_dividends_paid_b":     "raw_dividends_paid_b",
    "raw_net_debt_issuance_b":  "raw_net_debt_issuance_b",
}
for sk, ok in _raw_override_map.items():
    v = _ss(sk)
    if v is not None and v > 0:
        if sk == "raw_payout_pct":
            overrides["raw_payout_ratio"] = v / 100.0
        elif ok:
            overrides[ok] = v

# IV sub-model override
iv_model_choice = _ss("iv_model_sel", "auto")
if iv_model_choice and iv_model_choice != "auto":
    overrides["iv_model_override"] = iv_model_choice.lower()

# ── Compute ──────────────────────────────────────────────────────────────────
with st.spinner("Fetching data and computing..."):
    try:
        from src.valmod.pipeline import run_valuation
        out = run_valuation(ticker, overrides)
    except Exception as e:
        st.error(str(e))
        st.stop()

if "error" in out:
    st.error(out["error"])
    st.stop()

# ── Global variables ──────────────────────────────────────────────────────────
_MODEL_LABELS = {
    "damodaran_pe": "PE Regression",
    "damodaran_iv": "Intrinsic Value Discounting",
    "ev_ebitda":    "EV/EBITDA Multiple",
    "ev_sales":     "EV/Sales Multiple",
}

r = out["final_range"]
p = out.get("current_price")
mid = r.get("mid")
recommended_model = out.get("recommended_model", "damodaran_pe")
recommended_reason = out.get("recommended_reason", "")
sector = out.get("sector") or "Unknown"
industry = out.get("industry") or ""
mo = out.get("model_outputs", {})
fin = out.get("financials", {})
norm_out = out.get("normalized", {})
industry_str = f" / {industry}" if industry else ""

# ── 1. Core results ───────────────────────────────────────────────────────────
st.subheader("Valuation Results")

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Current Price", f"${p:.2f}" if p is not None else "N/A")
with c2:
    if r.get("low") and r.get("high"):
        st.metric("Valuation Range", f"${r['low']:.1f} – ${r['high']:.1f}")
    else:
        st.metric("Valuation Range", "N/A")
with c3:
    if p and r.get("low") and r.get("high"):
        if p < r["low"]:
            _gap = (r["low"] - p) / p
            st.metric("vs. Range", f"Below Low by {_gap:.1%}")
        elif p > r["high"]:
            _gap = (p - r["high"]) / p
            st.metric("vs. Range", f"Above High by {_gap:.1%}")
        else:
            _in_pct = (p - r["low"]) / (r["high"] - r["low"])
            st.metric("vs. Range", f"In Range ({_in_pct:.0%})")
    if r.get("divergence_alert"):
        st.warning("⚠ Relative valuation deviates >20% from intrinsic value — review WACC / growth rate")

# ── Recommended model summary ─────────────────────────────────────────────────
rec_label = _MODEL_LABELS.get(recommended_model, recommended_model)
_iv_val = mo.get("damodaran_iv")
_anchor_explain = (
    "**Valuation range anchor: Intrinsic Value Discounting (Model 3)**, with Relative Valuation (Model 2) as a cross-check."
    if _iv_val is not None
    else "Intrinsic value model not run (fill in Rf / ERP in the sidebar). Range is derived from available models."
)
st.info(
    f"**Recommended Model: {rec_label}**  |  Sector: {sector}{industry_str}\n\n"
    f"{recommended_reason}\n\n"
    f"{_anchor_explain}  ·  *Scenario analysis at the bottom of the page*"
)

# ─────────────────────────────────────────────────────────────────────────────
# ── 2. Model valuations (order: PE → Relative → IV) ──────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Individual Model Valuations")

_t = tax_rate_pct / 100      # tax rate (decimal)
_rf = rf_pct / 100
_erp = erp_pct / 100
_g_stable = g_stable_iv_pct / 100


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Model 1: PE Regression Valuation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
dam_pe = mo.get("damodaran_pe")
dam_det = mo.get("damodaran_pe_details") or {}

with st.container(border=True):
    st.markdown("**Model 1: PE Regression** (Damodaran January 2025 regression equation)")

    # Formula
    st.code(
        "PE = 24.17 − 1.07 × β + 53.16 × gEPS + 1.08 × Payout Ratio\n"
        "Target Price = PE × Diluted EPS\n"
        "β_levered = β_unlevered × [1 + (1 − t) × D/E]",
        language="",
    )

    col_params, col_results = st.columns([1, 1])

    with col_params:
        st.markdown("**Parameters**")

        # Parameter table (combined display)
        beta_used = dam_det.get("beta_used")
        beta_src = dam_det.get("beta_source", "")
        fin_beta = fin.get("beta")

        # Sector unlevered beta row: display depends on whether user filled it in
        if sector_beta_unlevered > 0:
            _beta_row = f"| Sector Unlevered β | **{sector_beta_unlevered:.2f}** | Sidebar (Damodaran) |"
        elif fin_beta is not None:
            _beta_row = f"| Sector Unlevered β | **0 → yfinance {fin_beta:.3f} (fallback)** | yfinance |"
        else:
            _beta_row = f"| Sector Unlevered β | **0 → yfinance beta unavailable** | — |"

        _levered_row = f"| Levered β (incl. D/E) | **{beta_used:.3f}** | Auto-derived |" if beta_used is not None else ""

        st.markdown(
            f"| Parameter | Value | Source |\n"
            f"|-----------|-------|--------|\n"
            f"| gEPS | **{gEPS_pct:.1f}%** | Sidebar |\n"
            f"{_beta_row}\n"
            + (f"{_levered_row}\n" if _levered_row else "")
            + f"| Tax Rate t | **{tax_rate_pct:.0f}%** | Sidebar |"
        )

        if sector_beta_unlevered == 0:
            st.caption(
                "💡 Sector unlevered beta: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html\n"
                "(Damodaran website, updated every January)"
            )

        # Payout ratio (from financials)
        fin_payout = fin.get("payout_ratio")
        if fin_payout is not None:
            st.markdown(
                f"| Parameter | Value | Source |\n"
                f"|-----------|-------|--------|\n"
                f"| Payout Ratio | **{fin_payout:.1%}** | Financials |"
            )
        else:
            st.markdown("⚠ **Payout Ratio** not found in financials (treat as 0% if company pays no dividends)")
            st.number_input(
                "Fill in: Payout Ratio (%)",
                min_value=0.0, max_value=100.0, value=0.0, step=0.5,
                format="%.1f",
                key="raw_payout_pct" + _sfx,
                help="Will auto-recalculate after input. 0% = no dividend, normal for growth companies.",
            )

        # Diluted EPS (from financials, most critical)
        fin_eps = fin.get("diluted_eps")
        if fin_eps is not None and fin_eps > 0:
            st.markdown(
                f"| Parameter | Value | Source |\n"
                f"|-----------|-------|--------|\n"
                f"| Diluted EPS | **${fin_eps:.2f}** | Financials |"
            )
        else:
            st.markdown("⚠ **Diluted EPS** not found or negative (must be > 0 to compute target price)")
            st.number_input(
                "Fill in: Diluted EPS ($/share)",
                min_value=0.0, max_value=1000.0, value=0.0, step=0.01,
                format="%.2f",
                key="raw_diluted_eps" + _sfx,
                help="From annual report EPS (diluted). E.g. AAPL 2024 ≈ $6.08. Leave 0 to not override.",
            )

    with col_results:
        st.markdown("**Results**")
        if dam_pe is not None:
            st.metric(
                "Target Price",
                f"${dam_pe:.1f}",
                delta=f"{(dam_pe - p) / p:+.1%}" if p else None,
            )
            d2, d3, d4 = st.columns(3)
            with d2:
                st.metric("Implied PE", f"{dam_det.get('pe_implied', 0):.1f}x")
            with d3:
                st.metric("β (levered)", f"{dam_det.get('beta_used', 0):.3f}")
            with d4:
                st.metric("Payout Ratio", f"{dam_det.get('payout_ratio', 0):.1%}")
            if dam_det.get("formula"):
                st.caption(f"Formula check: {dam_det['formula']}")
            if beta_src:
                st.caption(f"Beta source: {beta_src}")
        else:
            st.warning("Model cannot compute target price")
            missing_hints = []
            if fin_eps is None or (fin_eps is not None and fin_eps <= 0):
                missing_hints.append("Diluted EPS (fill in on the left)")
            if beta_used is None:
                missing_hints.append("Beta (check market cap data)")
            if missing_hints:
                st.caption("Missing: " + ", ".join(missing_hints))
            err_msg = dam_det.get("note", dam_det.get("error", ""))
            if err_msg:
                st.caption(f"Details: {err_msg}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Model 2: Relative Valuation (fundamentals-derived multiples)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
mult_det = mo.get("multiples_details") or {}
ev_ebitda_val = mo.get("ev_ebitda")
ev_sales_val = mo.get("ev_sales")
iv_anchor = mo.get("damodaran_iv")

# Determine WACC source
if iv_anchor is not None:
    _wacc_source = "Model 3 (intrinsic value) derived"
elif rf_pct:
    _wacc_source = "Rf / ERP parameter calculation"
else:
    _wacc_source = "Default fallback (10%)"

with st.container(border=True):
    st.markdown("**Model 2: Relative Valuation (fundamentals-derived multiples · confidence check)**")
    st.caption("Not used as a standalone conclusion — triggers a warning when deviation from intrinsic value exceeds 20%, prompting a review of assumptions.")

    # Formula
    st.code(
        "EV/EBIT = (1 − t) × (1 − RR) / (WACC − g)     ← EBIT ≈ EBITDA approximation\n"
        "EV/Sales = After-tax EBIT margin × (1 − RR) × (1 + g) / (WACC − g)\n"
        "RR (Reinvestment Rate) = max(CapEx − D&A, 0) / NOPAT",
        language="",
    )

    col_params2, col_results2 = st.columns([1, 1])

    with col_params2:
        st.markdown("**Parameters**")

        # WACC and macro parameters
        wacc_used = mult_det.get("wacc_used")
        g_used = mult_det.get("g_used")
        rr_used = mult_det.get("reinvestment_rate")
        atm_used = mult_det.get("after_tax_margin")

        macro_lines = (
            f"| Parameter | Value | Source |\n"
            f"|-----------|-------|--------|\n"
        )
        if wacc_used is not None:
            macro_lines += f"| WACC / re | **{wacc_used:.2%}** | {_wacc_source} |\n"
        macro_lines += (
            f"| g (perpetual growth) | **{g_stable_iv_pct:.1f}%** | Sidebar |\n"
            f"| Tax Rate t | **{tax_rate_pct:.0f}%** | Sidebar |"
        )
        st.markdown(macro_lines)

        if rr_used is not None:
            st.markdown(
                f"| Parameter | Value | Source |\n"
                f"|-----------|-------|--------|\n"
                f"| Reinvestment Rate RR | **{rr_used:.1%}** | Auto-derived |\n"
                + (f"| After-tax EBIT Margin | **{atm_used:.1%}** | Auto-derived |" if atm_used is not None else "")
            )

        st.markdown("**Financials**")

        # EBITDA
        fin_ebitda = fin.get("ebitda_b")
        if fin_ebitda is not None:
            st.markdown(f"• EBITDA: **${fin_ebitda:.1f}B** ← financials")
        else:
            st.markdown("⚠ **EBITDA** not found")
            st.number_input(
                "Fill in: EBITDA ($B)",
                min_value=0.0, value=0.0, step=0.5, format="%.1f",
                key="raw_ebitda_b" + _sfx,
                help="Leave 0 to not override.",
            )

        # Revenue
        fin_rev = fin.get("revenue_b")
        if fin_rev is not None:
            st.markdown(f"• Revenue: **${fin_rev:.1f}B** ← financials")
        else:
            st.markdown("⚠ **Revenue** not found")
            st.number_input(
                "Fill in: Revenue ($B)",
                min_value=0.0, value=0.0, step=1.0, format="%.1f",
                key="raw_revenue_b" + _sfx,
                help="Leave 0 to not override.",
            )

        # EBIT
        fin_ebit = fin.get("operating_income_b")
        if fin_ebit is not None:
            st.markdown(f"• EBIT (Operating Income): **${fin_ebit:.1f}B** ← financials")
        else:
            st.markdown("⚠ **EBIT (Operating Income)** not found")
            st.number_input(
                "Fill in: EBIT ($B)",
                min_value=0.0, value=0.0, step=0.5, format="%.1f",
                key="raw_operating_income_b" + _sfx,
                help="Leave 0 to not override.",
            )

        # CapEx & D&A (display, usually available)
        fin_capex = fin.get("capex_b")
        fin_da = fin.get("da_b")
        if fin_capex is not None:
            st.markdown(f"• CapEx: **${fin_capex:.1f}B** ← financials")
        if fin_da is not None:
            st.markdown(f"• D&A: **${fin_da:.1f}B** ← financials")

        # Net debt
        _net_debt_b = norm_out.get("net_debt")
        if _net_debt_b is not None:
            st.markdown(f"• Net Debt: **${_net_debt_b / 1e9:.1f}B** ← financials")

    with col_results2:
        st.markdown("**Results**")
        any_rel = False
        for label, key, mult_key in [
            ("EV/EBITDA Method", "ev_ebitda", "implied_ev_ebitda_mult"),
            ("EV/Sales Method",  "ev_sales",  "implied_ev_sales_mult"),
        ]:
            v = mo.get(key)
            mult_v = mult_det.get(mult_key)
            if v is not None:
                delta_str = f"{(v - p) / p:+.1%}" if p else None
                st.metric(label, f"${v:.1f}", delta=delta_str)
                if mult_v:
                    st.caption(f"Implied multiple: **{mult_v:.1f}×**")
                if iv_anchor and iv_anchor > 0:
                    dev = abs(v - iv_anchor) / iv_anchor
                    if dev > 0.20:
                        st.caption(
                            f"⚠ Deviation from intrinsic value: **{dev:.0%}** — review WACC"
                            f" ({mult_det.get('wacc_used', 0):.2%}) or g"
                        )
                any_rel = True

        if not any_rel:
            st.warning("Relative valuation unavailable")
            _has_ebitda = fin.get("ebitda_b") is not None
            _has_rev    = fin.get("revenue_b") is not None
            _impl_mult  = mult_det.get("implied_ev_ebitda_mult")
            _rr         = mult_det.get("reinvestment_rate")
            _net_debt_b = (norm_out.get("net_debt") or 0) / 1e9

            if _impl_mult is not None and _has_ebitda:
                # Model ran but equity value is negative (implied EV < net debt)
                _ev_b = _impl_mult * fin.get("ebitda_b", 0)
                if _ev_b < _net_debt_b and _net_debt_b > 0:
                    st.caption(
                        f"**Reason: Negative equity value**\n\n"
                        f"• Implied EV/EBITDA multiple = **{_impl_mult:.2f}×** (low; typical reference 8–15×)\n"
                        f"• Implied EV = **${_ev_b:.1f}B**  <  Net Debt = **${_net_debt_b:.1f}B**\n"
                        f"• Reinvestment Rate = **{_rr:.0%}** (high reinvestment compresses the multiple)\n\n"
                        f"Likely cause: CapEx far exceeds D&A, pushing reinvestment rate to the cap (95%).\n"
                        f"Consider using **Model 3 (Intrinsic Value Discounting)** instead."
                    )
                elif fin.get("shares_b") is None or (norm_out.get("shares_diluted") or 0) <= 0:
                    st.caption("Reason: **Diluted shares** missing — cannot convert to per-share value (fill in below).")
                else:
                    st.caption(f"Multiple computed ({_impl_mult:.1f}×), but per-share equity value is abnormal — check net debt data.")
            else:
                missing_rel = []
                if not _has_ebitda:
                    missing_rel.append("EBITDA (fill in on the left)")
                if not _has_rev:
                    missing_rel.append("Revenue (fill in on the left)")
                if missing_rel:
                    st.caption("Missing data: " + ", ".join(missing_rel))
                elif mult_det.get("wacc_used") is None:
                    st.caption("WACC not computed — fill in Rf / ERP in the sidebar.")

        if wacc_used:
            st.caption(
                f"Derived parameters: WACC={wacc_used:.2%}  g={g_used:.2%}"
                + (f"  RR={rr_used:.1%}" if rr_used is not None else "")
                + (f"  After-tax EBIT margin={atm_used:.1%}" if atm_used is not None else "")
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Model 3: Intrinsic Value Discounting (FCFF / FCFE / DDM)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
iv_val = mo.get("damodaran_iv")
iv_det = mo.get("damodaran_iv_details") or {}
_IV_MODEL_NAMES = {
    "fcff": "FCFF (Free Cash Flow to Firm)",
    "fcfe": "FCFE (Free Cash Flow to Equity)",
    "ddm":  "DDM (Dividend Discount Model)",
}
iv_model_used = iv_det.get("model_used", "").lower()
iv_model_label = _IV_MODEL_NAMES.get(iv_model_used, iv_model_used.upper() or "Not run")
auto_model = iv_det.get("auto_model", iv_model_used)
is_manual_override = iv_det.get("is_manual_override", False)

# _display_model: used for displaying the formula and financial data sections.
# When model fails (iv_model_used=""), falls back to the radio selection to avoid blank formula area.
_radio_val_iv = (_ss("iv_model_sel", "auto") or "auto").lower()
_display_model = iv_model_used if iv_model_used else (
    _radio_val_iv if _radio_val_iv != "auto" else ""
)

with st.container(border=True):
    st.markdown("**Model 3: Intrinsic Value Discounting** (valuation range anchor)")

    # ── Sub-model selector (radio) ─────────────────────────────────────────
    _auto_label = f"Auto-recommend ({auto_model.upper()})" if auto_model else "Auto-recommend"
    _iv_radio_opts = ["auto", "FCFF", "FCFE", "DDM"]
    _iv_radio_labels = {
        "auto":  _auto_label,
        "FCFF":  "FCFF — Free Cash Flow to Firm",
        "FCFE":  "FCFE — Free Cash Flow to Equity",
        "DDM":   "DDM — Dividend Discount Model",
    }
    st.radio(
        "Discounting sub-model",
        options=_iv_radio_opts,
        format_func=lambda x: _iv_radio_labels[x],
        horizontal=True,
        key="iv_model_sel" + _sfx,
        help=(
            "**Auto-recommend**: system automatically selects the most suitable sub-model based on financial characteristics\n\n"
            "• DDM: payout ratio >70% and debt/market cap <50% → mature cash cow\n"
            "• FCFF: loss-making or debt/market cap >80% → high-leverage / loss-making company\n"
            "• FCFE: all other cases → stable leverage with positive earnings\n\n"
            "You can manually switch to compare valuations across sub-models."
        ),
    )

    # ── Formula (shown per selected sub-model) ─────────────────────────────
    if _display_model == "fcff":
        st.code(
            "FCFF = EBIT × (1−t) − Net CapEx − ΔNon-cash WC\n"
            "WACC = re × E/(D+E) + rd × (1−t) × D/(D+E)\n"
            "re = Rf + β × ERP  ,  rd = Rf + Default Spread\n"
            "TV = FCFF_n × (1+g_stable) / (WACC − g_stable)\n"
            "Value per share = (EV − Total Debt + Cash) / Diluted Shares",
            language="",
        )
    elif _display_model == "fcfe":
        st.code(
            "FCFE = Net Income + D&A − CapEx − ΔWC + Net Debt Issuance\n"
            "re = Rf + β × ERP\n"
            "TV = FCFE_n × (1+g_stable) / (re − g_stable)\n"
            "Value per share = PV(FCFE high-growth) + PV(TV)",
            language="",
        )
    elif _display_model == "ddm":
        st.code(
            "DPS₀ = Dividends Paid / Shares  or  Diluted EPS × Payout Ratio\n"
            "re = Rf + β × ERP\n"
            "TV = DPS_n × (1+g_stable) / (re − g_stable)  [constraint: g_stable ≤ Rf]\n"
            "Value per share = Σ DPS_t/(1+re)^t + TV/(1+re)^n",
            language="",
        )
    else:
        st.caption("Fill in Rf / ERP and other parameters in the sidebar to run the intrinsic value model.")

    col_p3, col_r3 = st.columns([1, 1])

    with col_p3:
        # ── Macro parameters (from sidebar) ───────────────────────────────
        st.markdown("**Macro Parameters (Sidebar)**")
        macro3 = (
            f"| Parameter | Value |\n"
            f"|-----------|-------|\n"
            f"| Rf (risk-free rate) | **{rf_pct:.1f}%** |\n"
            f"| ERP (equity risk premium) | **{erp_pct:.1f}%** |\n"
            f"| Sector Unlevered β | **{sector_beta_unlevered:.2f}** |\n"
            f"| High Growth Rate g_high | **{g_high_iv_pct:.1f}%** |\n"
            f"| High Growth Period n | **{int(n_high_iv)} yrs** |\n"
            f"| Perpetual Growth g_stable | **{g_stable_iv_pct:.1f}%** (≤ Rf constraint) |"
        )
        if _display_model == "fcff":
            macro3 += f"\n| Default Spread | **{default_spread_pct:.1f}%** |"
        st.markdown(macro3)

        # ── Financials (different fields per sub-model) ────────────────────
        st.markdown("**Financials**")

        def _show_or_input(label, fin_key, ss_key, unit="$B", min_v=0.0, default_v=0.0, step=0.5, fmt="%.1f"):
            val = fin.get(fin_key)
            if val is not None and val > 0:
                st.markdown(f"• {label}: **${val:.2f}B** ← financials")
            else:
                st.markdown(f"⚠ **{label}** not found")
                st.number_input(
                    f"Fill in: {label} ({unit})",
                    min_value=min_v, value=default_v, step=step, format=fmt,
                    key=ss_key + _sfx,
                    help="Leave 0 to not override financials.",
                )

        def _show_val_optional(label, fin_key, unit="$B", allow_zero=False):
            """Display value (allow None or 0, no user input required)."""
            val = fin.get(fin_key)
            if val is not None:
                st.markdown(f"• {label}: **${val:.2f}B** ← financials")
            else:
                st.markdown(f"• {label}: — not found (treated as 0)")

        if _display_model == "fcff":
            _show_or_input("EBIT (Operating Income)", "operating_income_b", "raw_operating_income_b")
            _show_or_input("CapEx", "capex_b", "raw_capex_b")
            _show_or_input("D&A (Depreciation & Amortization)", "da_b", "raw_da_b")
            _show_or_input("Total Debt", "total_debt_b", "raw_total_debt_b")
            _show_or_input("Cash & Equivalents", "cash_b", "raw_cash_b")
            _show_or_input("Diluted Shares", "shares_b", "raw_shares_b", unit="B shares")
            _show_val_optional("Change in Working Capital (ΔWC)", "working_capital_b", allow_zero=True)

        elif _display_model == "fcfe":
            _show_or_input("Net Income", "net_income_b", "raw_net_income_b")
            _show_or_input("D&A (Depreciation & Amortization)", "da_b", "raw_da_b")
            _show_or_input("CapEx", "capex_b", "raw_capex_b")
            _show_or_input("Diluted Shares", "shares_b", "raw_shares_b", unit="B shares")
            # Net debt issuance (can be negative, allow 0)
            fin_ndi = fin.get("net_debt_issuance_b")
            if fin_ndi is not None:
                st.markdown(f"• Net Debt Issuance: **${fin_ndi:.2f}B** ← financials (negative = repayment)")
            else:
                st.markdown("• Net Debt Issuance: — not found (treated as 0)")
                st.number_input(
                    "Fill in: Net Debt Issuance ($B)",
                    min_value=-200.0, max_value=200.0, value=0.0, step=1.0, format="%.1f",
                    key="raw_net_debt_issuance_b" + _sfx,
                    help="Net new borrowing (proceeds minus repayments). Positive = net new debt, negative = net repayment.",
                )

        elif _display_model == "ddm":
            fin_div = fin.get("dividends_paid_b")
            fin_eps = fin.get("diluted_eps")
            fin_payout = fin.get("payout_ratio")
            if fin_div is not None and fin_div > 0:
                st.markdown(f"• Total Dividends Paid: **${fin_div:.2f}B** ← financials")
            elif fin_eps and fin_eps > 0 and fin_payout:
                st.markdown(f"• DPS₀ estimated from EPS (${fin_eps:.2f}) × Payout Ratio ({fin_payout:.1%})")
            else:
                st.markdown("⚠ **Dividend data (dividends paid / DPS)** not found")
                st.number_input(
                    "Fill in: Total Dividends Paid ($B)",
                    min_value=0.0, value=0.0, step=0.1, format="%.2f",
                    key="raw_dividends_paid_b" + _sfx,
                    help="Leave 0 to not override.",
                )
            _show_or_input("Diluted Shares", "shares_b", "raw_shares_b", unit="B shares")

    with col_r3:
        st.markdown("**Results**")
        if iv_val is not None:
            st.metric(
                "Target Price",
                f"${iv_val:.1f}",
                delta=f"{(iv_val - p) / p:+.1%}" if p else None,
            )
            r3a, r3b = st.columns(2)
            with r3a:
                if _display_model == "fcff":
                    st.metric("WACC", f"{iv_det.get('wacc', 0):.2%}")
                else:
                    st.metric("Cost of Equity re", f"{iv_det.get('re', 0):.2%}")
            with r3b:
                st.metric("Levered β", f"{iv_det.get('beta_levered', 0):.3f}")

            tp = iv_det.get("terminal_pct")
            color_iv = "🔴" if tp and tp > 0.70 else "🟡" if tp and tp > 0.55 else "🟢"
            st.metric("Terminal Value %", f"{color_iv} {tp:.0%}" if tp is not None else "N/A")

            # Cash flow detail
            if iv_model_used == "fcff" and iv_det.get("fcff_0_B") is not None:
                st.caption(
                    f"FCFF₀ = ${iv_det['fcff_0_B']:.2f}B  "
                    f"Net CapEx = ${iv_det.get('net_capex_B', 0):.2f}B  "
                    f"Equity Value = ${iv_det.get('equity_value_B', 0):.1f}B"
                )
            elif iv_model_used == "fcfe" and iv_det.get("fcfe_0_B") is not None:
                st.caption(
                    f"FCFE₀ = ${iv_det['fcfe_0_B']:.2f}B  "
                    f"Net Income = ${iv_det.get('net_income_B', 0):.2f}B"
                )
            elif iv_model_used == "ddm" and iv_det.get("dps_0") is not None:
                st.caption(
                    f"DPS₀ = ${iv_det['dps_0']:.2f}/share  "
                    f"Source: {iv_det.get('dps_source', '')}"
                )

            st.caption(
                f"g_stable = {iv_det.get('g_stable_used', 0):.2%}  |  "
                f"{'Manual override' if is_manual_override else 'Auto-selected'} {iv_model_used.upper()}\n\n"
                f"{iv_det.get('selection_reason', '')}"
            )
        else:
            _err = iv_det.get("error", "")
            _model_ran = bool(iv_det.get("model_used", ""))
            _disp = (_display_model or iv_model_used).lower()

            if _err:
                # Exception info (captured and injected by registry.py)
                st.warning(f"Model computation error: {_err}")
            elif _model_ran or _disp:
                # Model ran but returned None — give specific diagnosis per sub-model
                _diag = []
                if _disp == "fcff":
                    _ev_b2 = iv_det.get("equity_value_B")
                    if _ev_b2 is not None and _ev_b2 <= 0:
                        _nd2 = (norm_out.get("net_debt") or 0) / 1e9
                        _diag.append(f"Negative equity value (EV < Net Debt ${_nd2:.1f}B)")
                    if fin.get("operating_income_b") is None:
                        _diag.append("EBIT (Operating Income) missing → fill in Model 3 financials section")
                    if fin.get("shares_b") is None:
                        _diag.append("Diluted shares missing → fill in")
                elif _disp == "fcfe":
                    _ni = fin.get("net_income_b")
                    if _ni is None:
                        _diag.append("Net income missing → fill in Model 3 financials section")
                    elif _ni <= 0:
                        _diag.append(f"Net income is negative (${_ni:.2f}B); FCFE discounted value is negative")
                    if fin.get("shares_b") is None:
                        _diag.append("Diluted shares missing → fill in")
                elif _disp == "ddm":
                    _div = fin.get("dividends_paid_b")
                    _eps2 = fin.get("diluted_eps")
                    _pay2 = fin.get("payout_ratio")
                    if (_div is None or _div <= 0) and not (_eps2 and _eps2 > 0 and _pay2):
                        _diag.append("Dividend data missing (dividends paid / EPS×payout both unavailable) → fill in dividends paid")
                    if fin.get("shares_b") is None:
                        _diag.append("Diluted shares missing → fill in")
                _label = _disp.upper() if _disp else "IV"
                if _diag:
                    st.warning(f"Model unavailable ({_label}): " + "; ".join(_diag))
                else:
                    st.warning(f"Model unavailable ({_label}): discounted value is negative or cash flow data is abnormal")
            else:
                # Model not run (should not happen in practice since Rf/ERP always have defaults)
                st.warning("Insufficient parameters (fill in Rf / ERP in the sidebar)")


# ── 3. Alerts ─────────────────────────────────────────────────────────────────
alerts = out.get("alerts", [])
if alerts:
    st.subheader("Alerts")
    for a in alerts:
        msg = a.get("message", "")
        reason = a.get("reason", "")
        suggestion = a.get("suggestion", "")
        detail = f"  Reason: {reason}" + (f"  Suggestion: {suggestion}" if suggestion else "")
        if a.get("level") == "critical":
            st.error(f"🔴 {msg}{detail}")
        else:
            st.warning(f"🟡 {msg}{detail}")

# ── 4. Data quality ───────────────────────────────────────────────────────────
with st.expander("Data Quality"):
    dq = out.get("data_quality", {})
    st.write(f"Completeness: {dq.get('completeness', 0):.0%}")
    if dq.get("missing"):
        st.caption("Missing fields: " + ", ".join(dq["missing"]))
    if dq.get("critical"):
        for c in dq["critical"]:
            st.error(c)
    if dq.get("warnings"):
        for w in dq["warnings"]:
            st.warning(w)

# ── 5. Full JSON (debug) ──────────────────────────────────────────────────────
with st.expander("Full Data (Debug)"):
    st.json(out)

# ── 6. Scenario analysis (bottom, based on recommended model) ─────────────────
st.markdown("---")
st.subheader("Scenario Analysis")

mo_sc = out.get("model_outputs", {})
norm_sc = out.get("normalized", {})
rec_label_sc = _MODEL_LABELS.get(recommended_model, recommended_model)

st.markdown(
    f"**Recommended Model: {rec_label_sc}**  |  Sector: {sector}{industry_str}\n\n"
    f"The following generates Bear / Base / Bull scenarios by adjusting key parameters of **{rec_label_sc}**."
)

# ----- PE regression scenarios -----
if recommended_model == "damodaran_pe":
    dam_det_sc = mo_sc.get("damodaran_pe_details") or {}
    beta_sc = dam_det_sc.get("beta_used")
    payout_sc = dam_det_sc.get("payout_ratio", 0.0)
    eps_sc = dam_det_sc.get("diluted_eps")
    _INT, _B_c, _G, _P = 24.17, -1.07, 53.16, 1.08

    def _dam_price(gEPS):
        if beta_sc is None or not eps_sc or eps_sc <= 0:
            return None
        pe = _INT + _B_c * beta_sc + _G * gEPS + _P * payout_sc
        return pe * eps_sc if pe > 0 else None

    gEPS_def = gEPS_pct / 100
    _beta_str = f"{beta_sc:.3f}" if beta_sc is not None else "N/A"
    _eps_str = f"{eps_sc:.2f}" if eps_sc else "N/A"
    st.caption(f"Adjustment variable: **Expected EPS Growth gEPS** (β={_beta_str}, payout={payout_sc:.1%}, diluted EPS=${_eps_str})")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_g = st.number_input("Bear gEPS (%)", value=round((gEPS_def - 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_bear_g") / 100
    with sc2:
        base_g = st.number_input("Base gEPS (%)", value=round(gEPS_def * 100, 1), step=0.5, format="%.1f", key="sc_base_g") / 100
    with sc3:
        bull_g = st.number_input("Bull gEPS (%)", value=round((gEPS_def + 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_bull_g") / 100
    sc_prices = [(_dam_price(bear_g), "Bear", "#EF4444"), (_dam_price(base_g), "Base", "#F59E0B"), (_dam_price(bull_g), "Bull", "#22C55E")]

# ----- Intrinsic value discounting scenarios -----
elif recommended_model == "damodaran_iv":
    iv_det_sc = mo_sc.get("damodaran_iv_details") or {}
    iv_model_sc = iv_det_sc.get("model_used", "").lower()
    re_sc = iv_det_sc.get("re", 0.10)
    wacc_sc = iv_det_sc.get("wacc", re_sc)
    g_stable_sc = iv_det_sc.get("g_stable_used", 0.025)

    st.caption(f"Adjustment variable: **High Growth Rate g_high** (model={iv_model_sc.upper()}, discount rate={wacc_sc if iv_model_sc == 'fcff' else re_sc:.2%}, g_stable={g_stable_sc:.2%})")

    g_high_def = g_high_iv_pct / 100
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_gh = st.number_input("Bear g_high (%)", value=round((g_high_def - 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_iv_bear") / 100
    with sc2:
        base_gh = st.number_input("Base g_high (%)", value=round(g_high_def * 100, 1), step=0.5, format="%.1f", key="sc_iv_base") / 100
    with sc3:
        bull_gh = st.number_input("Bull g_high (%)", value=round((g_high_def + 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_iv_bull") / 100

    def _iv_approx(g_high_new):
        if iv_val is None or g_high_def == 0:
            return None
        ratio = (1 + g_high_new) / (1 + g_high_def)
        return iv_val * ratio

    sc_prices = [
        (_iv_approx(bear_gh), "Bear", "#EF4444"),
        (_iv_approx(base_gh), "Base", "#F59E0B"),
        (_iv_approx(bull_gh), "Bull", "#22C55E"),
    ]

# ----- EV/EBITDA scenarios -----
elif recommended_model == "ev_ebitda":
    ebitda_sc = norm_sc.get("ebitda")
    nd_sc = norm_sc.get("net_debt", 0) or 0
    sh_sc = norm_sc.get("shares_diluted")

    def _eveb_price(anchor):
        if not ebitda_sc or not sh_sc or ebitda_sc <= 0 or sh_sc <= 0:
            return None
        eq = anchor * ebitda_sc - nd_sc
        return eq / sh_sc if eq > 0 else None

    st.caption(f"Adjustment variable: **EV/EBITDA multiple** (EBITDA=${ebitda_sc / 1e9:.2f}B, Net Debt=${nd_sc / 1e9:.2f}B)" if ebitda_sc else "EV/EBITDA data unavailable")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_anch = st.number_input("Bear EV/EBITDA (×)", value=10.0, step=0.5, format="%.1f", key="sc_bear_ev")
    with sc2:
        base_anch = st.number_input("Base EV/EBITDA (×)", value=12.0, step=0.5, format="%.1f", key="sc_base_ev")
    with sc3:
        bull_anch = st.number_input("Bull EV/EBITDA (×)", value=14.0, step=0.5, format="%.1f", key="sc_bull_ev")
    sc_prices = [(_eveb_price(bear_anch), "Bear", "#EF4444"), (_eveb_price(base_anch), "Base", "#F59E0B"), (_eveb_price(bull_anch), "Bull", "#22C55E")]

# ----- EV/Sales scenarios -----
else:
    rev_sc = norm_sc.get("revenue")
    nd_sc = norm_sc.get("net_debt", 0) or 0
    sh_sc = norm_sc.get("shares_diluted")

    def _evs_price(anchor):
        if not rev_sc or not sh_sc or rev_sc <= 0 or sh_sc <= 0:
            return None
        eq = anchor * rev_sc - nd_sc
        return eq / sh_sc if eq > 0 else None

    st.caption(f"Adjustment variable: **EV/Sales multiple** (Revenue=${rev_sc / 1e9:.2f}B, Net Debt=${nd_sc / 1e9:.2f}B)" if rev_sc else "EV/Sales data unavailable")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_anch = st.number_input("Bear EV/Sales (×)", value=3.0, step=0.5, format="%.1f", key="sc_bear_evs")
    with sc2:
        base_anch = st.number_input("Base EV/Sales (×)", value=5.0, step=0.5, format="%.1f", key="sc_base_evs")
    with sc3:
        bull_anch = st.number_input("Bull EV/Sales (×)", value=7.0, step=0.5, format="%.1f", key="sc_bull_evs")
    sc_prices = [(_evs_price(bear_anch), "Bear", "#EF4444"), (_evs_price(base_anch), "Base", "#F59E0B"), (_evs_price(bull_anch), "Bull", "#22C55E")]

# ----- Scenario results display -----
valid_sc = [(v, lab, col) for v, lab, col in sc_prices if v is not None]
if valid_sc:
    m1, m2, m3 = st.columns(3)
    for col_obj, (v, lab, _) in zip([m1, m2, m3], sc_prices):
        with col_obj:
            if v is not None:
                delta = f"{(v - p) / p:+.1%}" if p else None
                st.metric(lab, f"${v:.1f}", delta=delta)
            else:
                st.metric(lab, "N/A")

    fig_sc2 = go.Figure()
    for v, lab, col in sc_prices:
        if v is not None:
            fig_sc2.add_trace(go.Bar(name=lab, x=[lab], y=[v], marker_color=col, width=0.4))
    if p:
        fig_sc2.add_hline(y=p, line_dash="dash", line_color="white",
                          annotation_text=f"Current Price ${p:.1f}", annotation_position="top left")
    fig_sc2.update_layout(
        height=320, showlegend=False, margin=dict(l=20, r=20, t=40, b=20),
        yaxis_title="Valuation ($)",
        title=f"Three-Scenario Valuation vs Current Price ({rec_label_sc})",
    )
    st.plotly_chart(fig_sc2, use_container_width=True)
else:
    st.warning("Insufficient data for scenario analysis — check data quality or switch models.")

# ── 7. Quotes ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    """
<div style="text-align: center; color: #888; font-size: 0.85em; line-height: 2.2em; padding: 12px 0 4px 0;">

善战者无赫赫之功 ——《孙子兵法》<br>
<em>The supreme warrior wins without celebrated feats. — Sun Tzu</em>

<br>

做一个战争型而不是战斗型的选手，我们不需要每天都有新主意，需要关心的是如何将一个正确的主意数年如一日地做好，"不抛弃，不放弃"是真的大不易。——杨天南<br>
<em>Be a strategist, not just a fighter. We don't need a new idea every day — what matters is executing one right idea with unwavering consistency for years. To never abandon, never give up, is truly no small feat. — Yang Tiannan</em>

<br>

价值投资者的悲哀在于，即便他们以价值作为行为方式的前提，他们的记分牌却是价格。——杨天南<br>
<em>The tragedy of value investors is that, even though they take value as the premise of their actions, their scorecard is price. — Yang Tiannan</em>

</div>
""",
    unsafe_allow_html=True,
)
