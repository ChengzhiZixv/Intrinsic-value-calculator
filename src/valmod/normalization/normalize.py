# =============================================================================
# Layer 2 - 标准化层（normalize.py）
# =============================================================================
# 职责：将 RawData 转为可估值的 NormalizedFinancials。
# 处理：FCF=CFO-CAPEX、净债务、比率、股本保底、CAPEX 保底。
# 所有估算都会记录在 transform_log 中，供你核对。
#
# 你可调整：
# - 无业务参数。若会计科目名变化，可在此修改映射。
# =============================================================================

from typing import Optional

from src.valmod.types import RawData, NormalizedFinancials


def normalize(raw: RawData) -> NormalizedFinancials:
    """
    标准化原始数据。
    输入：RawData
    输出：NormalizedFinancials（含 transform_log 记录所有计算与估算）
    """
    log = []

    # ----- 股本：优先 info，缺失时用 市值/股价 反推 -----
    shares_diluted = raw.shares
    if shares_diluted is None and raw.market_cap is not None and raw.current_price is not None and raw.current_price > 0:
        shares_diluted = raw.market_cap / raw.current_price
        log.append("股本由 市值/股价 反推估计（标注：股本反推估计）")

    # ----- CAPEX 保底：缺失时用 PPE 净额年度变化近似 -----
    capex = raw.capex
    if capex is None and raw.ppe_net is not None and raw.ppe_net_prior is not None:
        capex = -(raw.ppe_net - raw.ppe_net_prior)
        log.append("CAPEX 由 PPE 净额年度变化近似（受折旧/处置/并购影响，标注：CAPEX估算）")

    # ----- FCF = CFO - CAPEX（CAPEX 为负时，FCF = CFO + |CAPEX|）-----
    fcf = None
    if raw.cfo is not None:
        if capex is not None:
            fcf = raw.cfo + capex if capex < 0 else raw.cfo - capex
        else:
            log.append("CAPEX 缺失且无法估算，FCF 无法计算，DCF 将禁用")
    else:
        log.append("CFO 缺失，FCF 无法计算，DCF 将禁用")

    # ----- 净债务 = Total Debt - Cash -----
    net_debt = None
    if raw.total_debt is not None and raw.cash is not None:
        net_debt = raw.total_debt - raw.cash

    # ----- 比率（能算则算）-----
    fcf_margin = None
    if fcf is not None and raw.revenue is not None and raw.revenue > 0:
        fcf_margin = fcf / raw.revenue

    ebitda_margin = None
    if raw.ebitda is not None and raw.revenue is not None and raw.revenue > 0:
        ebitda_margin = raw.ebitda / raw.revenue

    roe = None
    if raw.net_income is not None and raw.market_cap is not None and raw.market_cap > 0:
        roe = raw.net_income / raw.market_cap

    return NormalizedFinancials(
        ticker=raw.ticker,
        fcf=fcf,
        net_debt=net_debt,
        revenue=raw.revenue,
        ebitda=raw.ebitda,
        net_income=raw.net_income,
        fcf_margin=fcf_margin,
        ebitda_margin=ebitda_margin,
        roe=roe,
        shares_diluted=shares_diluted,
        period_type="annual",
        transform_log=log,
    )
