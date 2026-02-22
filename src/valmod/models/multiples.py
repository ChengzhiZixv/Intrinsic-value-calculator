# =============================================================================
# Layer 5 - 相对估值（multiples.py）
# =============================================================================
# 职责：基本面推导 EV/EBITDA 与 EV/Sales 倍数，不再使用主观锚定值。
#
# 核心哲学（Damodaran）：
#   倍数本质上是 DCF 的浓缩——任何合理的倍数都可以从基本面推导，
#   而非"行业经验值 12x"这种主观数字。
#
# EV/EBITDA 推导：
#   EV/EBIT = (1-t)(1-RR) / (WACC-g)          ← FCFF Gordon 模型的变形
#   注：此处将 EBIT ≈ EBITDA（忽略 D&A 差异）作为近似
#
# EV/Sales 推导：
#   EV/Sales = 税后EBIT利润率 × (1-RR) × (1+g) / (WACC-g)
#
# 其中 RR（再投资率）= Net CapEx / NOPAT = (CapEx - D&A) / (EBIT × (1-t))
# WACC 优先使用 Damodaran IV 模型中计算的值（通过 overrides["_computed_wacc"] 传入）
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, RawData


def run_multiples(
    norm: NormalizedFinancials,
    raw: RawData,
    overrides: Optional[dict] = None,
) -> dict:
    """
    基本面驱动的相对估值（EV/EBITDA、EV/Sales）。
    倍数由 WACC、g、再投资率、税后利润率推导，而非硬编码。

    overrides 关键字段：
      _computed_wacc  - 优先：由 Damodaran IV 模型计算的 WACC/re
      rf, erp, default_spread, beta - 备用：用于自行计算 re/WACC
      g_stable_iv     - 永续增长率
      tax_rate        - 边际税率
    """
    overrides = overrides or {}
    tax_rate = overrides.get("tax_rate", 0.25)
    g = overrides.get("g_stable_iv", 0.025)

    # ── 1. 获取折现率 ─────────────────────────────────────────────────────────
    # 优先使用 Damodaran IV 已计算的 WACC（企业层面），否则退而用 re 近似
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
        wacc = 0.10  # 最终保底默认

    if wacc <= g:
        g = max(wacc - 0.005, 0.005)  # 防止除零，修正 g

    # ── 2. 计算再投资率（Net CapEx / NOPAT） ──────────────────────────────────
    capex = abs(raw.capex or 0)
    da = raw.depreciation_amortization or 0
    ebit = raw.operating_income or 0
    nopat = ebit * (1 - tax_rate)
    net_capex = max(capex - da, 0)

    if nopat > 0:
        reinv_rate = net_capex / nopat
        reinv_rate = max(0.0, min(reinv_rate, 0.95))  # 截断至合理范围
    else:
        reinv_rate = 0.30  # 无法计算时保守假设 30%

    # ── 3. 基本面推导 EV/EBITDA 倍数 ─────────────────────────────────────────
    # 公式：(1-t)(1-RR) / (WACC-g)
    implied_ev_ebitda_mult = (1 - tax_rate) * (1 - reinv_rate) / (wacc - g)
    implied_ev_ebitda_mult = max(implied_ev_ebitda_mult, 0)

    ev_ebitda_val = None
    if raw.ebitda and raw.ebitda > 0 and norm.shares_diluted and norm.shares_diluted > 0:
        ev_implied = implied_ev_ebitda_mult * raw.ebitda
        equity_val = ev_implied - (norm.net_debt or 0)
        ev_ebitda_val = equity_val / norm.shares_diluted if equity_val > 0 else None

    # ── 4. 基本面推导 EV/Sales 倍数 ──────────────────────────────────────────
    # 公式：税后EBIT利润率 × (1-RR) × (1+g) / (WACC-g)
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
# Damodaran PE 回归模型（2025年1月）
# 公式：PE = 24.17 - 1.07×Beta + 53.16×gEPS + 1.08×PayoutRatio
# 参考：Aswath Damodaran, January 2025 PE regression
# =============================================================================

# [可调] 回归系数（来自 Damodaran 2025年1月数据）
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
    Damodaran PE 回归估值（2025年1月版本）。
    PE = 24.17 - 1.07×Beta + 53.16×gEPS + 1.08×PayoutRatio
    目标价 = PE × 稀释EPS

    参数：
      gEPS                  - 预期EPS年增速（小数，如 0.10 = 10%）
      sector_beta_unlevered - 行业无杠杆Beta（来自Damodaran官网）；为None时用yfinance回归Beta
      tax_rate              - 边际税率，默认25%
    """
    # ── 1. 计算 Beta ────────────────────────────────────────────────────────
    if sector_beta_unlevered is not None and raw.market_cap and raw.market_cap > 0:
        d_e = (raw.total_debt or 0) / raw.market_cap
        beta_used = sector_beta_unlevered * (1 + (1 - tax_rate) * d_e)
        beta_source = "Damodaran bottom-up（行业无杠杆Beta加杠杆）"
    elif raw.beta is not None:
        beta_used = raw.beta
        beta_source = "yfinance 回归Beta（备用）"
    else:
        return {"damodaran_pe": None, "damodaran_pe_details": None}

    # ── 2. 派息率 ────────────────────────────────────────────────────────────
    payout = raw.payout_ratio if raw.payout_ratio is not None else 0.0

    # ── 3. 回归公式 ──────────────────────────────────────────────────────────
    pe_implied = _INTERCEPT + _COEF_BETA * beta_used + _COEF_GEPS * gEPS + _COEF_PAYOUT * payout

    if pe_implied <= 0:
        return {"damodaran_pe": None, "damodaran_pe_details": {
            "pe_implied": pe_implied, "beta": beta_used, "gEPS": gEPS,
            "payout_ratio": payout, "note": "回归PE为负，不适用"
        }}

    # ── 4. 目标价 = PE × 稀释EPS ─────────────────────────────────────────────
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
