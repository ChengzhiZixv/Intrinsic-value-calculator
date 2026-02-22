# =============================================================================
# Layer 7 - 模型融合（weighting.py）
# =============================================================================
# 核心逻辑：以 Damodaran IV（FCFF/FCFE/DDM）为内在价值锚，
#           相对估值（EV/EBITDA、EV/Sales）和 PE 回归作为置信区间验证。
#
# 聚合规则：
#   1. 若 Damodaran IV 可用 → mid = IV；低/高 = 所有模型最小/最大值
#      任何相对估值与 IV 偏差 > IV_DIVERGENCE_THRESHOLD → divergence_alert
#   2. 若 IV 不可用、但 Damodaran PE 可用 → mid = PE，区间同上
#   3. 兜底：等权平均所有可用模型
#
# 你可调整：
# - IV_DIVERGENCE_THRESHOLD：相对估值与内在价值的偏差告警阈值（默认 20%）
# - SPREAD_ALERT_THRESHOLD：所有模型最大偏差超过此阈值也告警（默认 30%）
# =============================================================================

from src.valmod.types import ModelOutputs, FinalRange

IV_DIVERGENCE_THRESHOLD = 0.20   # 相对估值与 IV 偏差 >20% → 告警
SPREAD_ALERT_THRESHOLD  = 0.30   # 全模型区间宽度 >30% of mid → 告警


def aggregate(models: ModelOutputs) -> FinalRange:
    """
    IV 锚定聚合：以内在价值为中枢，相对估值作置信区间。
    输入：ModelOutputs
    输出：FinalRange
    """
    contributions = {}
    if models.damodaran_iv is not None:
        contributions["damodaran_iv"] = models.damodaran_iv
    if models.damodaran_pe is not None:
        contributions["damodaran_pe"] = models.damodaran_pe
    if models.ev_ebitda is not None:
        contributions["ev_ebitda"] = models.ev_ebitda
    if models.ev_sales is not None:
        contributions["ev_sales"] = models.ev_sales

    values = list(contributions.values())
    if not values:
        return FinalRange(low=0.0, mid=0.0, high=0.0, model_contributions=contributions,
                          weight_explain="无可用模型", divergence_alert=False)

    # ── 确定 mid ─────────────────────────────────────────────────────────────
    if models.damodaran_iv is not None:
        mid = models.damodaran_iv
        anchor_name = "Damodaran IV（内在价值）"
    elif models.damodaran_pe is not None:
        mid = models.damodaran_pe
        anchor_name = "Damodaran PE（内在价值模型未运行）"
    else:
        mid = sum(values) / len(values)
        anchor_name = f"等权平均（{len(values)} 个模型）"

    # ── 偏差检查：相对估值与锚点的距离 ────────────────────────────────────────
    divergence_alert = False
    if mid and mid > 0:
        relative_keys = [k for k in contributions if k not in ("damodaran_iv", "damodaran_pe")]
        for k in relative_keys:
            dev = abs(contributions[k] - mid) / mid
            if dev > IV_DIVERGENCE_THRESHOLD:
                divergence_alert = True
                break
        # 也检查全局区间宽度
        v_min, v_max = min(values), max(values)
        if (v_max - v_min) / mid > SPREAD_ALERT_THRESHOLD:
            divergence_alert = True

    v_min = min(values)
    v_max = max(values)
    low = v_min if len(values) > 1 else mid * 0.85
    high = v_max if len(values) > 1 else mid * 1.15

    weight_explain = f"{anchor_name}锚定｜区间 = 所有模型最小–最大值"

    return FinalRange(
        low=low,
        mid=mid,
        high=high,
        model_contributions=contributions,
        weight_explain=weight_explain,
        divergence_alert=divergence_alert,
    )
