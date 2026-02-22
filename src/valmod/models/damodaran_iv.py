# =============================================================================
# Layer 5 - 达莫达兰内在价值模型（damodaran_iv.py）
# =============================================================================
# 职责：根据公司财务特征自动选择并运行三种达莫达兰内在价值模型之一：
#   FCFF（公司自由现金流）、FCFE（股权自由现金流）、DDM（股利贴现）
#
# 选择逻辑（参考 Damodaran 教学框架）：
#   DDM ：派息率 > 70% 且 债/市值 < 50%  ← 成熟现金奶牛（如可口可乐）
#   FCFF：债/市值 > 80% 或 净利润 ≤ 0    ← 高杠杆/亏损（FCFE 受还债扰动过大）
#   FCFE：其余情况                        ← 杠杆稳定且盈利
#
# 关键参数（由用户在侧边栏填入，overrides 传入）：
#   rf              - 无风险利率（10 年期美债收益率）
#   erp             - 股权风险溢价（Damodaran 每月更新，美股约 4.2–4.5%）
#   default_spread  - 违约利差（根据公司信用评级查询，如 BBB ≈ 1.5–2.0%）
#   sector_beta_unlevered - 行业无杠杆 Beta（来自 damodaran.com）
#   tax_rate        - 边际税率
#   g_high_iv       - 高速增长期增长率
#   n_high_iv       - 高速增长期年数（成熟公司 5 年，成长型 10 年）
#   g_stable_iv     - 永续增长率（必须 ≤ 无风险利率 Rf，通常 2–3%）
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, RawData


# ── 模型选择 ──────────────────────────────────────────────────────────────────

def select_damodaran_model(raw: RawData) -> tuple:
    """
    根据公司财务特征选择最适合的达莫达兰内在价值模型。
    返回：(model_name, reason_str)
      model_name ∈ {"fcff", "fcfe", "ddm"}
    """
    net_income = raw.net_income or 0
    total_debt = raw.total_debt or 0
    market_cap = raw.market_cap or 1
    payout_ratio = raw.payout_ratio or 0
    D_ratio = total_debt / market_cap if market_cap > 0 else 0

    if payout_ratio > 0.7 and D_ratio < 0.5:
        return (
            "ddm",
            f"派息率 {payout_ratio:.1%} > 70% 且 债/市值 {D_ratio:.1%} < 50%，"
            "符合成熟现金奶牛特征，DDM（股利贴现）最适合",
        )
    elif D_ratio > 0.8 or net_income <= 0:
        reason = "净利润为负或零" if net_income <= 0 else f"债/市值 {D_ratio:.1%} > 80%"
        return (
            "fcff",
            f"{reason}，高杠杆/亏损结构下 FCFF（公司自由现金流）更稳健",
        )
    else:
        return (
            "fcfe",
            f"杠杆稳定（债/市值 {D_ratio:.1%}）且净利润为正，FCFE（股权自由现金流）直接衡量股东回报",
        )


# ── 共用参数提取 ──────────────────────────────────────────────────────────────

def _beta_and_cost_of_equity(raw: RawData, params: dict) -> tuple:
    """
    返回 (beta_levered, re, error_str_or_None)
    re = Rf + β_levered × ERP
    β_levered = β_unlevered × (1 + (1 - t) × D/E)
    """
    Rf = params.get("rf", 0.045)
    ERP = params.get("erp", 0.045)
    beta_unlevered = params.get("sector_beta_unlevered", 1.0)
    t = params.get("tax_rate", 0.25)

    total_debt = raw.total_debt or 0
    market_cap = raw.market_cap or 0
    if market_cap <= 0:
        return (None, None, "市值不可得，无法计算 Beta")

    D_E = total_debt / market_cap
    beta_levered = beta_unlevered * (1 + (1 - t) * D_E)
    re = Rf + beta_levered * ERP
    return (beta_levered, re, None)


# ── FCFF 模型 ─────────────────────────────────────────────────────────────────

def run_fcff(raw: RawData, params: dict) -> dict:
    """
    FCFF = EBIT×(1-t) - Net CapEx - ΔNon-cash WC
    折现率：WACC = re×E/(D+E) + rd×(1-t)×D/(D+E)
    rd = Rf + Default Spread
    终值：TV = FCFF_n × (1+g_stable) / (WACC - g_stable)
    每股价值 = (EV - 总债务 + 现金) / 股本
    """
    Rf = params.get("rf", 0.045)
    default_spread = params.get("default_spread", 0.02)
    t = params.get("tax_rate", 0.25)
    g_high = params.get("g_high_iv", 0.10)
    n_high = int(params.get("n_high_iv", 5))
    g_stable = params.get("g_stable_iv", 0.025)
    g_stable = min(g_stable, Rf)  # 强制约束 g ≤ Rf

    # ── 数据校验 ──
    ebit = raw.operating_income
    if not ebit or ebit <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": "EBIT 不可得或非正，FCFF 不适用"}}

    beta_levered, re, err = _beta_and_cost_of_equity(raw, params)
    if err:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFF", "error": err}}

    total_debt = raw.total_debt or 0
    market_cap = raw.market_cap or 1
    cash = raw.cash or 0
    shares = raw.shares or 0
    if shares <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFF", "error": "股本不可得"}}

    # ── WACC ──
    V = market_cap + total_debt
    E_w = market_cap / V
    D_w = total_debt / V
    rd = Rf + default_spread
    wacc = re * E_w + rd * (1 - t) * D_w

    if wacc <= g_stable:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": f"WACC({wacc:.2%}) ≤ g_stable({g_stable:.2%})，终值无意义"}}

    # ── FCFF_0 ──
    capex_abs = abs(raw.capex) if raw.capex is not None else 0
    depr = abs(raw.depreciation_amortization) if raw.depreciation_amortization is not None else 0
    net_capex = capex_abs - depr

    delta_wc = 0.0
    if raw.working_capital is not None and raw.working_capital_prior is not None:
        delta_wc = raw.working_capital - raw.working_capital_prior

    fcff_0 = ebit * (1 - t) - net_capex - delta_wc
    if fcff_0 <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": f"FCFF_0={fcff_0/1e9:.2f}B 为负，FCFF 不适用（考虑改用 FCFE）"}}

    # ── 高速增长期 PV ──
    pv_high = sum(fcff_0 * (1 + g_high) ** i / (1 + wacc) ** i for i in range(1, n_high + 1))

    # ── 终值 ──
    fcff_n = fcff_0 * (1 + g_high) ** n_high
    tv = fcff_n * (1 + g_stable) / (wacc - g_stable)
    pv_tv = tv / (1 + wacc) ** n_high

    # ── 每股权益价值 ──
    ev = pv_high + pv_tv
    equity_value = ev - total_debt + cash
    if equity_value <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFF", "error": "权益价值为负（债务超过 EV）", "ev": round(ev / 1e9, 2)}}

    value_per_share = equity_value / shares

    return {
        "damodaran_iv": value_per_share,
        "damodaran_iv_details": {
            "model_used": "FCFF",
            "beta_levered": round(beta_levered, 3),
            "re": round(re, 4),
            "rd": round(rd, 4),
            "wacc": round(wacc, 4),
            "fcff_0_B": round(fcff_0 / 1e9, 3),
            "net_capex_B": round(net_capex / 1e9, 3),
            "delta_wc_B": round(delta_wc / 1e9, 3),
            "ev_B": round(ev / 1e9, 2),
            "equity_value_B": round(equity_value / 1e9, 2),
            "terminal_pct": round(pv_tv / ev, 4) if ev > 0 else None,
            "g_stable_used": round(g_stable, 4),
        },
    }


# ── FCFE 模型 ─────────────────────────────────────────────────────────────────

def run_fcfe(raw: RawData, params: dict) -> dict:
    """
    FCFE = 净利润 + D&A - CapEx - ΔWC + 净债务融资
    折现率：re（股权成本，CAPM）
    终值：TV = FCFE_n × (1+g_stable) / (re - g_stable)
    每股价值 = PV(FCFE) / 股本
    """
    Rf = params.get("rf", 0.045)
    t = params.get("tax_rate", 0.25)
    g_high = params.get("g_high_iv", 0.10)
    n_high = int(params.get("n_high_iv", 5))
    g_stable = params.get("g_stable_iv", 0.025)
    g_stable = min(g_stable, Rf)

    net_income = raw.net_income
    if not net_income or net_income <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFE", "error": "净利润不可得或非正，FCFE 不适用"}}

    beta_levered, re, err = _beta_and_cost_of_equity(raw, params)
    if err:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFE", "error": err}}

    if re <= g_stable:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFE", "error": f"re({re:.2%}) ≤ g_stable({g_stable:.2%})"}}

    shares = raw.shares or 0
    if shares <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "FCFE", "error": "股本不可得"}}

    depr = abs(raw.depreciation_amortization) if raw.depreciation_amortization is not None else 0
    capex_abs = abs(raw.capex) if raw.capex is not None else 0
    delta_wc = 0.0
    if raw.working_capital is not None and raw.working_capital_prior is not None:
        delta_wc = raw.working_capital - raw.working_capital_prior
    net_debt_iss = raw.net_debt_issuance or 0

    fcfe_0 = net_income + depr - capex_abs - delta_wc + net_debt_iss
    if fcfe_0 <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "FCFE", "error": f"FCFE_0={fcfe_0/1e9:.2f}B 为负（考虑改用 FCFF）"}}

    pv_high = sum(fcfe_0 * (1 + g_high) ** i / (1 + re) ** i for i in range(1, n_high + 1))
    fcfe_n = fcfe_0 * (1 + g_high) ** n_high
    tv = fcfe_n * (1 + g_stable) / (re - g_stable)
    pv_tv = tv / (1 + re) ** n_high

    equity_value = pv_high + pv_tv
    value_per_share = equity_value / shares

    return {
        "damodaran_iv": value_per_share,
        "damodaran_iv_details": {
            "model_used": "FCFE",
            "beta_levered": round(beta_levered, 3),
            "re": round(re, 4),
            "fcfe_0_B": round(fcfe_0 / 1e9, 3),
            "net_income_B": round(net_income / 1e9, 3),
            "depr_B": round(depr / 1e9, 3),
            "capex_B": round(capex_abs / 1e9, 3),
            "delta_wc_B": round(delta_wc / 1e9, 3),
            "net_debt_iss_B": round(net_debt_iss / 1e9, 3),
            "equity_value_B": round(equity_value / 1e9, 2),
            "terminal_pct": round(pv_tv / equity_value, 4) if equity_value > 0 else None,
            "g_stable_used": round(g_stable, 4),
        },
    }


# ── DDM 模型 ──────────────────────────────────────────────────────────────────

def run_ddm(raw: RawData, params: dict) -> dict:
    """
    DDM：每股价值 = PV(DPS 高速增长期) + PV(终值)
    终值：TV = DPS_n × (1+g_stable) / (re - g_stable)
    约束：g_stable ≤ Rf（无风险利率）
    DPS 来源：优先用已派息金额/股本，其次用 EPS × 派息率
    """
    Rf = params.get("rf", 0.045)
    t = params.get("tax_rate", 0.25)
    g_high = params.get("g_high_iv", 0.05)   # DDM 的高速增长通常较低
    n_high = int(params.get("n_high_iv", 5))
    g_stable = params.get("g_stable_iv", 0.025)
    g_stable = min(g_stable, Rf)  # 强制：g ≤ Rf

    beta_levered, re, err = _beta_and_cost_of_equity(raw, params)
    if err:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "DDM", "error": err}}

    if re <= g_stable:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "DDM", "error": f"re({re:.2%}) ≤ g_stable({g_stable:.2%})"}}

    shares = raw.shares or 0
    if shares <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {"model_used": "DDM", "error": "股本不可得"}}

    # ── DPS ──
    dps = None
    dps_source = ""
    if raw.dividends_paid is not None and shares > 0:
        dps = raw.dividends_paid / shares
        dps_source = "现金流量表实际派息"
    elif raw.diluted_eps is not None and raw.payout_ratio is not None:
        dps = raw.diluted_eps * raw.payout_ratio
        dps_source = "EPS × 派息率估算"

    if not dps or dps <= 0:
        return {"damodaran_iv": None, "damodaran_iv_details": {
            "model_used": "DDM", "error": "DPS 不可得或为零（公司未派息，DDM 不适用）"}}

    pv_high = sum(dps * (1 + g_high) ** i / (1 + re) ** i for i in range(1, n_high + 1))
    dps_n = dps * (1 + g_high) ** n_high
    tv = dps_n * (1 + g_stable) / (re - g_stable)
    pv_tv = tv / (1 + re) ** n_high

    value_per_share = pv_high + pv_tv

    return {
        "damodaran_iv": value_per_share,
        "damodaran_iv_details": {
            "model_used": "DDM",
            "beta_levered": round(beta_levered, 3),
            "re": round(re, 4),
            "dps_0": round(dps, 4),
            "dps_source": dps_source,
            "g_stable_used": round(g_stable, 4),
            "g_stable_constraint": f"g_stable 已限制 ≤ Rf({Rf:.2%})",
            "terminal_pct": round(pv_tv / value_per_share, 4) if value_per_share > 0 else None,
        },
    }


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_damodaran_iv(raw: RawData, params: dict) -> dict:
    """
    自动选择 FCFF/FCFE/DDM 并运行，返回内在价值估算结果。
    输入：RawData, params（含 rf/erp/default_spread/sector_beta_unlevered 等）
    输出：{damodaran_iv, damodaran_iv_details}
      details 含 model_used, selection_reason, auto_model, is_manual_override 等
    支持 params["iv_model_override"] ∈ {"fcff","fcfe","ddm"} 强制指定子模型。
    """
    # 始终运行自动选择逻辑（即使被覆盖，也保留推荐结果供 UI 展示）
    auto_model, auto_reason = select_damodaran_model(raw)

    model_override = (params.get("iv_model_override") or "").lower().strip()
    if model_override in ("fcff", "fcfe", "ddm"):
        model_name = model_override
        selection_reason = f"用户手动指定 {model_name.upper()}（自动推荐：{auto_model.upper()}）"
        is_manual = True
    else:
        model_name = auto_model
        selection_reason = auto_reason
        is_manual = False

    if model_name == "fcff":
        result = run_fcff(raw, params)
    elif model_name == "fcfe":
        result = run_fcfe(raw, params)
    else:
        result = run_ddm(raw, params)

    # 注入元信息
    if result.get("damodaran_iv_details") is not None:
        result["damodaran_iv_details"]["selection_reason"] = selection_reason
        result["damodaran_iv_details"]["auto_model"] = auto_model
        result["damodaran_iv_details"]["is_manual_override"] = is_manual

    return result
