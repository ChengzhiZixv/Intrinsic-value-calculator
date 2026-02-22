# =============================================================================
# Layer 3 - 分类与模型选择（selector.py）
# =============================================================================
# 职责：根据数据可得性决定启用哪些估值模型，并根据行业推荐首选模型。
# 规则：EBITDA 可得 → EV/EBITDA；Revenue → EV/Sales（传统 DCF 已移除）。
# 推荐逻辑：根据 yfinance sector 字段映射至行业最惯用的估值方法。
#
# 你可调整：
# - _SECTOR_RECOMMEND：行业 → 推荐模型的映射表
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, SelectionResult

# 行业 → 推荐模型映射（基于行业估值惯例）
# key 与 yfinance info["sector"] 保持一致
_SECTOR_RECOMMEND: dict = {
    "Technology":             ("damodaran_pe", "科技行业以EPS成长驱动，Damodaran PE回归最契合行业估值惯例"),
    "Communication Services": ("damodaran_pe", "传媒科技以EPS成长驱动，Damodaran PE回归最契合行业估值惯例"),
    "Healthcare":             ("damodaran_pe", "医疗行业高成长特性，Damodaran PE回归较为适合"),
    "Consumer Defensive":     ("damodaran_pe", "消费防御型盈利稳健，PE估值为行业主流"),
    "Financial Services":     ("damodaran_pe", "金融行业以PE为主要估值方式"),
    "Consumer Cyclical":      ("ev_ebitda",    "消费周期行业波动大，EV/EBITDA去除周期性折旧更为稳定"),
    "Industrials":            ("ev_ebitda",    "工业企业资本密集，EV/EBITDA剔除折旧摊销更能反映经营价值"),
    "Basic Materials":        ("ev_ebitda",    "原材料行业，EV/EBITDA更能反映真实经营价值"),
    "Energy":                 ("damodaran_iv", "能源行业现金流稳定可预测，FCFF内在价值模型最为严谨"),
    "Utilities":              ("damodaran_iv", "公用事业现金流规律，FCFF内在价值模型最为适合"),
    "Real Estate":            ("damodaran_iv", "房地产以现金流估值为主，FCFF内在价值模型最为适合"),
}


def select_models(norm: NormalizedFinancials, sector: Optional[str] = None) -> SelectionResult:
    """
    根据标准化数据决定可用模型，并根据行业推荐首选估值方法。
    输入：NormalizedFinancials, sector（来自 yfinance info["sector"]）
    输出：SelectionResult（enabled_models, rationale, recommended_model, recommended_reason）
    """
    enabled = []
    rationale_parts = []

    # ----- 规则 1：EBITDA 可得 → 启用 EV/EBITDA -----
    if norm.ebitda is not None and norm.ebitda > 0:
        enabled.append("ev_ebitda")
        rationale_parts.append("EBITDA 可得，启用 EV/EBITDA")

    # ----- 规则 2：Revenue 可得 → 启用 EV/Sales -----
    if norm.revenue is not None and norm.revenue > 0:
        enabled.append("ev_sales")
        rationale_parts.append("收入可得，启用 EV/Sales")

    enabled = list(dict.fromkeys(enabled))

    if not enabled:
        rationale_parts.append("关键字段不足，无法估值")

    # ----- 行业推荐模型 -----
    if sector and sector in _SECTOR_RECOMMEND:
        recommended_model, recommended_reason = _SECTOR_RECOMMEND[sector]
    else:
        # 无行业信息时：优先 damodaran_pe（需 EPS），否则 ev_ebitda
        if norm.net_income is not None:
            recommended_model = "damodaran_pe"
            recommended_reason = "行业未识别，以 Damodaran PE 为默认首选（需填入 gEPS）"
        else:
            recommended_model = "ev_ebitda"
            recommended_reason = "行业未识别，以 EV/EBITDA 为备选"

    return SelectionResult(
        enabled_models=enabled,
        rationale="；".join(rationale_parts),
        recommended_model=recommended_model,
        recommended_reason=recommended_reason,
    )
