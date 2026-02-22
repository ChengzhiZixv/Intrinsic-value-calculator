# =============================================================================
# Layer 8 - 智能告警与上下文（context.py）
# =============================================================================
# 职责：生成分级告警（Critical/Warning）、估值不确定性告警、激进会计检测。
#
# 你可调整（下方常量）：
# - TERMINAL_PCT_WARN：终值占比告警阈值
# - DIVERGENCE_WARN：模型分歧告警阈值
# - DA_REVENUE_THRESHOLD：折旧/收入比率异常阈值
# - FCF_NI_RATIO_FLOOR：FCF/净利润长期偏低阈值
# =============================================================================

from typing import Optional

from src.valmod.types import DataQualityReport, ModelOutputs, RawData, NormalizedFinancials, AlertItem

TERMINAL_PCT_WARN = 0.70
DIVERGENCE_WARN = 0.30
DA_REVENUE_THRESHOLD = 0.15
FCF_NI_RATIO_FLOOR = 0.5


def build_warnings(
    quality: DataQualityReport,
    models: ModelOutputs,
    terminal_pct: Optional[float],
    raw: Optional[RawData] = None,
    norm: Optional[NormalizedFinancials] = None,
) -> list:
    """
    生成分级告警列表。
    输入：quality, models, terminal_pct, raw, norm
    输出：AlertItem 列表
    """
    alerts = []

    for c in quality.critical:
        alerts.append(AlertItem(level="critical", message=c, reason="数据质量", affected_models=[], suggestion="请核对数据源"))

    for w in quality.warnings:
        alerts.append(AlertItem(level="warning", message=w, reason="数据质量", affected_models=[], suggestion=""))

    if terminal_pct is not None and terminal_pct > TERMINAL_PCT_WARN:
        alerts.append(AlertItem(
            level="warning",
            message=f"终值占比 {terminal_pct:.1%} 超过 {TERMINAL_PCT_WARN:.0%}",
            reason="估值高度依赖长期假设",
            affected_models=["damodaran_iv"],
            suggestion="建议人工复核永续增长与折现率",
        ))

    if models.model_warnings:
        for mw in models.model_warnings:
            alerts.append(AlertItem(level="warning", message=mw, reason="模型输出", affected_models=[], suggestion=""))

    if raw is not None and norm is not None:
        if raw.depreciation_amortization is not None and raw.revenue is not None and raw.revenue > 0:
            da_ratio = raw.depreciation_amortization / raw.revenue
            if da_ratio > DA_REVENUE_THRESHOLD:
                alerts.append(AlertItem(
                    level="warning",
                    message=f"折旧/收入比率 {da_ratio:.1%} 较高",
                    reason="PE 类估值可能失真",
                    affected_models=["damodaran_pe"],
                    suggestion="需核对维持性资本开支与资产处置",
                ))

        if norm.fcf is not None and norm.net_income is not None and norm.net_income > 0:
            ratio = norm.fcf / norm.net_income
            if ratio < FCF_NI_RATIO_FLOOR:
                alerts.append(AlertItem(
                    level="warning",
                    message=f"FCF/净利润 {ratio:.2f} 偏低",
                    reason="盈利与现金流脱节",
                    affected_models=["damodaran_iv"],
                    suggestion="建议核对经营现金流质量",
                ))

    return alerts
