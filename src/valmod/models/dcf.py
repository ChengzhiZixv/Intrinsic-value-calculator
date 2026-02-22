# =============================================================================
# Layer 5 - DCF 估值模型（dcf.py）
# =============================================================================
# 职责：FCFF 模型，5 年显式期 + Gordon 终值，计算每股估值。
# 公式：每股价值 = (显式期现值 + 终值现值) / 稀释股本
# 终值：TV = FCF5 * (1+g) / (r - g)
#
# 你可调整（通过 Assumptions 或 config）：
# - discount_rate：折现率 r [ANALYST_REQUIRED]
# - perpetual_growth：永续增长 g [ANALYST_REQUIRED]
# - explicit_growth_rate：显式期增长率
# - explicit_years：显式期年数
# - TERMINAL_PCT_WARN：终值占比超过此阈值时告警（默认 70%）
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, Assumptions

# [可调] 终值占比超过此比例时触发 Warning
TERMINAL_PCT_WARN = 0.70


def run_dcf(norm: NormalizedFinancials, assumptions: Assumptions) -> dict:
    """
    DCF 估值。
    输入：NormalizedFinancials, Assumptions
    输出：{value_per_share, terminal_pct, warnings}
    """
    warnings = []

    if norm.fcf is None or norm.fcf <= 0:
        return {"value_per_share": None, "terminal_pct": None, "warnings": ["FCF 不可得或非正，DCF 不适用"]}

    if norm.shares_diluted is None or norm.shares_diluted <= 0:
        return {"value_per_share": None, "terminal_pct": None, "warnings": ["股本不可得，无法计算每股估值"]}

    r = assumptions.discount_rate
    g = assumptions.perpetual_growth
    gr = assumptions.explicit_growth_rate
    n = assumptions.explicit_years

    if r <= g:
        return {"value_per_share": None, "terminal_pct": None, "warnings": [f"折现率 r={r:.2%} 必须大于永续增长 g={g:.2%}"]}

    # ----- 显式期 FCF 预测 -----
    fcf0 = norm.fcf
    pv_explicit = 0.0
    for i in range(1, n + 1):
        fcf_i = fcf0 * ((1 + gr) ** i)
        pv_explicit += fcf_i / ((1 + r) ** i)

    # ----- 终值（Gordon Growth）-----
    fcf_n = fcf0 * ((1 + gr) ** n)
    terminal_value = fcf_n * (1 + g) / (r - g)
    pv_terminal = terminal_value / ((1 + r) ** n)

    # ----- 企业价值与每股估值 -----
    ev = pv_explicit + pv_terminal
    value_per_share = ev / norm.shares_diluted

    terminal_pct = pv_terminal / (pv_explicit + pv_terminal) if (pv_explicit + pv_terminal) > 0 else 0.0
    if terminal_pct > TERMINAL_PCT_WARN:
        warnings.append(f"终值占比 {terminal_pct:.1%} 超过 {TERMINAL_PCT_WARN:.0%}，估值高度依赖长期假设")

    return {
        "value_per_share": value_per_share,
        "terminal_pct": terminal_pct,
        "warnings": warnings,
    }
