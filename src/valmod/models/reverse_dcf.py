# =============================================================================
# Layer 5 - 反向 DCF（reverse_dcf.py）
# =============================================================================
# 职责：给定当前股价，反推「要撑起这个价格，未来 5 年 FCF 需要多高增速」。
# 输出：隐含 CAGR、第 5 年 FCF、隐含 FCF margin 与历史对比。
#
# 你可调整：无业务参数，逻辑固定。
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, Assumptions

try:
    from scipy.optimize import brentq as _brentq
    _SCIPY = True
except ImportError:
    _SCIPY = False


def run_reverse_dcf(
    norm: NormalizedFinancials,
    assumptions: Assumptions,
    current_price: float,
) -> dict:
    """
    反向 DCF：反推隐含 FCF 增速。
    输入：NormalizedFinancials, Assumptions, current_price
    输出：{implied_cagr, implied_fcf5, implied_margin_vs_historical}
    """
    if norm.fcf is None or norm.fcf <= 0:
        return {"implied_cagr": None, "implied_fcf5": None, "implied_margin_vs_historical": None}

    if norm.shares_diluted is None or norm.shares_diluted <= 0:
        return {"implied_cagr": None, "implied_fcf5": None, "implied_margin_vs_historical": None}

    r = assumptions.discount_rate
    g = assumptions.perpetual_growth
    n = assumptions.explicit_years

    if r <= g:
        return {"implied_cagr": None, "implied_fcf5": None, "implied_margin_vs_historical": None}

    ev_implied = current_price * norm.shares_diluted

    # 二分法反推 CAGR：使得 DCF 估值 = current_price
    def dcf_value(cagr: float) -> float:
        pv_explicit = 0.0
        fcf0 = norm.fcf
        for i in range(1, n + 1):
            fcf_i = fcf0 * ((1 + cagr) ** i)
            pv_explicit += fcf_i / ((1 + r) ** i)
        fcf_n = fcf0 * ((1 + cagr) ** n)
        tv = fcf_n * (1 + g) / (r - g)
        pv_terminal = tv / ((1 + r) ** n)
        return pv_explicit + pv_terminal

    try:
        if _SCIPY:
            # brentq 精确求根，比手写二分法更快更准
            implied_cagr = _brentq(
                lambda c: dcf_value(c) - ev_implied,
                -0.50, 0.50, xtol=1e-8, maxiter=200,
            )
        else:
            # 降级：手写二分法
            low, high = -0.50, 0.50
            for _ in range(60):
                mid = (low + high) / 2
                if dcf_value(mid) > ev_implied:
                    low = mid
                else:
                    high = mid
            implied_cagr = (low + high) / 2
    except Exception:
        return {"implied_cagr": None, "implied_fcf5": None, "implied_margin_vs_historical": None}
    implied_fcf5 = norm.fcf * ((1 + implied_cagr) ** n)

    implied_margin_vs_historical = None
    if norm.revenue is not None and norm.revenue > 0:
        historical_margin = norm.fcf / norm.revenue if norm.fcf else None
        implied_revenue_5 = norm.revenue * ((1 + implied_cagr) ** n)
        implied_margin_5 = implied_fcf5 / implied_revenue_5 if implied_revenue_5 > 0 else None
        if historical_margin is not None and implied_margin_5 is not None:
            implied_margin_vs_historical = {
                "historical_fcf_margin": historical_margin,
                "implied_fcf_margin_year5": implied_margin_5,
                "note": "若隐含 margin 显著高于历史，需评估增长假设合理性",
            }

    return {
        "implied_cagr": implied_cagr,
        "implied_fcf5": implied_fcf5,
        "implied_margin_vs_historical": implied_margin_vs_historical,
    }
