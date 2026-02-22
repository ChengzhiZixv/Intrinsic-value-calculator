# =============================================================================
# Layer 6 - 情景与敏感性引擎（engine.py）
# =============================================================================
# 职责：生成 Bear/Base/Bull 三情景，及单变量敏感性表。
# 扰动：增长率 ±2%，折现率 ±1%，永续增长 ±0.5%。
#
# 你可调整（下方常量）：
# - GROWTH_SHOCK：增长率扰动幅度
# - RATE_SHOCK：折现率扰动幅度
# - G_SHOCK：永续增长扰动幅度
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, Assumptions, ModelOutputs
from src.valmod.models.dcf import run_dcf

# [可调] 参数扰动幅度
GROWTH_SHOCK = 0.02
RATE_SHOCK = 0.01
G_SHOCK = 0.005


def run_scenarios(
    norm: NormalizedFinancials,
    assumptions: Assumptions,
    base_value: Optional[float] = None,
) -> dict:
    """
    三情景 + 单变量敏感性。
    输入：norm, assumptions, base_value（可选，若为 None 则用 DCF 基准值）
    输出：{low, mid, high, sensitivity}
    """
    r = assumptions.discount_rate
    g = assumptions.perpetual_growth
    gr = assumptions.explicit_growth_rate

    base_res = run_dcf(norm, assumptions)
    mid = base_value if (base_value is not None and base_value > 0) else (base_res.get("value_per_share") or 0.0)
    low = mid
    high = mid

    # ----- Bear：增长率-2%，r+1%，g-0.5% -----
    try:
        a_bear = Assumptions(
            discount_rate=r + RATE_SHOCK,
            perpetual_growth=g - G_SHOCK,
            explicit_years=assumptions.explicit_years,
            explicit_growth_rate=gr - GROWTH_SHOCK,
        )
        res = run_dcf(norm, a_bear)
        if res.get("value_per_share") is not None:
            low = res["value_per_share"]
        elif mid > 0:
            low = mid * 0.85
    except Exception:
        if mid > 0:
            low = mid * 0.85

    # ----- Bull：增长率+2%，r-1%，g+0.5% -----
    try:
        a_bull = Assumptions(
            discount_rate=max(0.01, r - RATE_SHOCK),
            perpetual_growth=g + G_SHOCK,
            explicit_years=assumptions.explicit_years,
            explicit_growth_rate=gr + GROWTH_SHOCK,
        )
        res = run_dcf(norm, a_bull)
        if res.get("value_per_share") is not None:
            high = res["value_per_share"]
        elif mid > 0:
            high = mid * 1.15
    except Exception:
        if mid > 0:
            high = mid * 1.15

    # ----- 单变量敏感性：增长率、折现率 -----
    sensitivity = {}
    try:
        a_gr_up = Assumptions(discount_rate=r, perpetual_growth=g, explicit_years=assumptions.explicit_years, explicit_growth_rate=gr + GROWTH_SHOCK)
        a_gr_down = Assumptions(discount_rate=r, perpetual_growth=g, explicit_years=assumptions.explicit_years, explicit_growth_rate=gr - GROWTH_SHOCK)
        a_r_up = Assumptions(discount_rate=r + RATE_SHOCK, perpetual_growth=g, explicit_years=assumptions.explicit_years, explicit_growth_rate=gr)
        a_r_down = Assumptions(discount_rate=max(0.01, r - RATE_SHOCK), perpetual_growth=g, explicit_years=assumptions.explicit_years, explicit_growth_rate=gr)

        v_gr_up = run_dcf(norm, a_gr_up).get("value_per_share")
        v_gr_down = run_dcf(norm, a_gr_down).get("value_per_share")
        v_r_up = run_dcf(norm, a_r_up).get("value_per_share")
        v_r_down = run_dcf(norm, a_r_down).get("value_per_share")

        if v_gr_up and v_gr_down and base_value > 0:
            sensitivity["growth_up"] = (v_gr_up - base_value) / base_value
            sensitivity["growth_down"] = (v_gr_down - base_value) / base_value
        if v_r_up and v_r_down and base_value > 0:
            sensitivity["rate_up"] = (v_r_up - base_value) / base_value
            sensitivity["rate_down"] = (v_r_down - base_value) / base_value
    except Exception:
        pass

    return {
        "low": low,
        "mid": mid,
        "high": high,
        "sensitivity": sensitivity,
    }
