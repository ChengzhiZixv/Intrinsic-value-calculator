# =============================================================================
# Layer 4 - 假设引擎（engine.py）
# =============================================================================
# 职责：生成默认估值假设；支持用户覆盖；记录假设来源。
# 默认：r=10%, g=2.5%, 显式期=5年，增长率=历史CAGR或5%。
#
# 你可调整（通过 config/analyst_overrides.yaml 或 overrides 参数）：
# - discount_rate：折现率 [ANALYST_REQUIRED]
# - perpetual_growth：永续增长 [ANALYST_REQUIRED]
# - explicit_years：显式预测年数
# - explicit_growth_rate：显式期增长率 [ANALYST_REQUIRED]
# - CAGR 上下限（CAGR_CAP, CAGR_FLOOR）防止极端值
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, Assumptions

# [可调] 历史 CAGR 上限，防止极端高增长
CAGR_CAP = 0.15
# [可调] 历史 CAGR 下限，负增长公司
CAGR_FLOOR = -0.10
# [可调] 算不出 CAGR 时的默认增长率
DEFAULT_GROWTH = 0.05


def _compute_revenue_cagr(norm: NormalizedFinancials) -> Optional[float]:
    """
    计算收入 CAGR。当前仅有最近一年 revenue，无法算多年 CAGR。
    若有历史序列可在此扩展；否则返回 None。
    """
    return None


def _compute_fcf_cagr(norm: NormalizedFinancials) -> Optional[float]:
    """计算 FCF CAGR。同上，单年数据无法算 CAGR。"""
    return None


def build_assumptions(norm: NormalizedFinancials, overrides: Optional[dict] = None) -> Assumptions:
    """
    生成估值假设。
    输入：NormalizedFinancials, overrides（可选，覆盖默认）
    输出：Assumptions + assumption_log
    """
    overrides = overrides or {}
    log = []

    # ----- 显式期增长率：优先历史 CAGR，否则默认 5% -----
    cagr = _compute_revenue_cagr(norm) or _compute_fcf_cagr(norm)
    if cagr is not None:
        cagr = max(CAGR_FLOOR, min(CAGR_CAP, cagr))
        explicit_growth = cagr
        log.append(f"显式期增长率=历史CAGR {cagr:.2%}（来源：默认计算）")
    else:
        explicit_growth = overrides.get("explicit_growth_rate", DEFAULT_GROWTH)
        log.append(f"显式期增长率=默认 {explicit_growth:.2%}（来源：保守默认值，无历史CAGR）")

    discount_rate = overrides.get("discount_rate", 0.10)
    perpetual_growth = overrides.get("perpetual_growth", 0.025)
    explicit_years = overrides.get("explicit_years", 5)

    log.append(f"折现率={discount_rate:.2%}（来源：{'用户覆盖' if 'discount_rate' in overrides else '默认'}）")
    log.append(f"永续增长={perpetual_growth:.2%}（来源：{'用户覆盖' if 'perpetual_growth' in overrides else '默认'}）")
    log.append(f"显式期年数={explicit_years}（来源：{'用户覆盖' if 'explicit_years' in overrides else '默认'}）")

    return Assumptions(
        discount_rate=discount_rate,
        perpetual_growth=perpetual_growth,
        explicit_years=explicit_years,
        explicit_growth_rate=explicit_growth,
        assumption_log=log,
    )
