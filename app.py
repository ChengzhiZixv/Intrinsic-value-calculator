"""
US Equity Valuation (learning tool). Run: streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="US Equity Valuation", layout="wide")
st.title("美股估值工具")

ticker = st.text_input(
    "股票代码（Ticker）",
    value="",
    max_chars=10,
    placeholder="例：AAPL  PLTR  ORCL  MSFT",
)

if not ticker or not ticker.strip():
    st.info("请输入股票代码后自动计算。")
    st.stop()

ticker = ticker.strip().upper()

# ── 侧边栏：宏观估值参数 ────────────────────────────────────────────────────
with st.sidebar:
    st.header("估值参数")

    # ── 模型一：PE 回归估值 ───────────────────────────────────────────────────
    st.markdown("#### 模型一：PE 回归估值")
    st.caption("以下参数**仅供 PE 回归模型使用**。税率也被内在价值模型共用。")

    gEPS_pct = st.number_input(
        "预期 EPS 增速 gEPS（%）　★必填",
        min_value=-20.0, max_value=100.0, value=10.0, step=0.5,
        format="%.1f",
        help=(
            "你预期该公司未来的 EPS 年增速。\n\n"
            "PE 回归中影响最大的变量（回归系数 53.16）。\n"
            "通常参考卖方一致预期或历史 EPS 增速，范围 5–20%。"
        ),
    )

    sector_beta_unlevered = st.number_input(
        "行业无杠杆 Beta　★必填",
        min_value=0.10, max_value=3.00, value=1.15, step=0.05,
        format="%.2f",
        help=(
            "行业平均无杠杆 Beta（从 damodaran.com 查询）。\n\n"
            "软件/云 ≈ 1.15，消费 ≈ 0.80，金融 ≈ 0.40。\n"
            "系统自动用公司债务/市值比加杠杆，得到公司层面 Beta。"
        ),
    )

    tax_rate_pct = st.number_input(
        "边际税率（%）　[模型一 + 模型三 共用]",
        min_value=0.0, max_value=40.0, value=25.0, step=1.0,
        format="%.0f",
        help=(
            "美国联邦+州综合税率，通常取 25%。\n\n"
            "PE 回归：用于计算加杠杆 Beta。\n"
            "内在价值折现：用于计算 NOPAT、WACC、再投资率。"
        ),
    )

    st.markdown("---")
    st.caption("*模型二（相对估值）无需额外参数——倍数由模型三 WACC 和财报数据自动推导*")
    st.markdown("---")

    # ── 模型三：内在价值折现（FCFF / FCFE / DDM） ────────────────────────────
    st.markdown("#### 模型三：内在价值折现（FCFF / FCFE / DDM）")
    st.caption(
        "以下参数**仅供内在价值折现模型使用**，"
        "同时也会传给模型二的 EV/EBITDA 和 EV/Sales 倍数推导。"
    )

    rf_pct = st.number_input(
        "无风险利率 Rf（%）　★必填",
        min_value=0.5, max_value=10.0, value=4.5, step=0.1,
        format="%.1f",
        help=(
            "通常取 10 年期美债收益率（当前约 4–5%）。\n\n"
            "用途：CAPM 基准收益率 → 计算股权成本 re = Rf + β × ERP。\n"
            "约束：永续增长率 g_stable 必须 ≤ Rf。"
        ),
    )

    erp_pct = st.number_input(
        "股权风险溢价 ERP（%）　★必填",
        min_value=1.0, max_value=10.0, value=4.5, step=0.1,
        format="%.1f",
        help=(
            "股票相对无风险资产的超额回报预期，美股约 4.2–4.5%。\n\n"
            "用途：re = Rf + β × ERP → 用于折现股权现金流（FCFE / DDM）"
            " 及 WACC 中的股权成本部分（FCFF）。"
        ),
    )

    default_spread_pct = st.number_input(
        "违约利差 Default Spread（%）　[仅 FCFF 使用]",
        min_value=0.0, max_value=10.0, value=1.5, step=0.1,
        format="%.1f",
        help=(
            "根据公司信用评级查询。\n\n"
            "用途：税前债务成本 rd = Rf + Default Spread → 计算 WACC。\n"
            "BBB 级 ≈ 1.5–2.0%，A 级 ≈ 0.8–1.2%，BB 级 ≈ 2.5–3.5%。\n"
            "仅在系统选择 FCFF 模型时有效；FCFE / DDM 不使用此项。"
        ),
    )

    g_high_iv_pct = st.number_input(
        "高速增长率（%）　★必填",
        min_value=0.0, max_value=40.0, value=10.0, step=0.5,
        format="%.1f",
        help=(
            "高速增长阶段的年增速（FCFF/FCFE 对应 FCF 增速，DDM 对应 DPS 增速）。\n\n"
            "可参考分析师一致预期或历史增速，通常 5–20%。"
        ),
    )

    n_high_iv = st.number_input(
        "高速增长年数　★必填",
        min_value=1, max_value=15, value=5, step=1,
        format="%d",
        help=(
            "高速增长阶段持续年数，之后进入永续增长。\n\n"
            "成熟公司建议 5 年，高成长型公司可取 7–10 年。"
        ),
    )

    g_stable_iv_pct = st.number_input(
        "永续增长率 g_stable（%）　★必填",
        min_value=0.0, max_value=5.0, value=2.5, step=0.1,
        format="%.1f",
        help=(
            "高速增长结束后的永续增长率（约等于名义 GDP 增速）。\n\n"
            "硬约束：系统自动强制 g_stable ≤ Rf，防止终值爆炸。\n"
            "通常取 2–3%，不宜超过 Rf。"
        ),
    )

# ── Session state 键后缀（按 ticker 隔离，避免换股残留）────────────────────
_sfx = f"__{ticker}"


def _ss(key, default=None):
    """读取 ticker 绑定的 session state 值。"""
    return st.session_state.get(key + _sfx, default)


# ── 汇总 overrides（侧边栏 + 内联补填数据）─────────────────────────────────
overrides = {
    "gEPS": gEPS_pct / 100,
    "sector_beta_unlevered": sector_beta_unlevered,
    "tax_rate": tax_rate_pct / 100,
    "rf": rf_pct / 100,
    "erp": erp_pct / 100,
    "default_spread": default_spread_pct / 100,
    "g_high_iv": g_high_iv_pct / 100,
    "n_high_iv": int(n_high_iv),
    "g_stable_iv": g_stable_iv_pct / 100,
}

# 内联财报覆盖（从上次渲染的卡片输入框读取）
_raw_override_map = {
    # key_suffix → overrides_key
    "raw_diluted_eps":          "raw_diluted_eps",
    "raw_payout_pct":           None,   # 特殊处理（%→小数）
    "raw_operating_income_b":   "raw_operating_income_b",
    "raw_capex_b":              "raw_capex_b",
    "raw_da_b":                 "raw_da_b",
    "raw_net_income_b":         "raw_net_income_b",
    "raw_total_debt_b":         "raw_total_debt_b",
    "raw_cash_b":               "raw_cash_b",
    "raw_shares_b":             "raw_shares_b",
    "raw_ebitda_b":             "raw_ebitda_b",
    "raw_revenue_b":            "raw_revenue_b",
    "raw_dividends_paid_b":     "raw_dividends_paid_b",
    "raw_net_debt_issuance_b":  "raw_net_debt_issuance_b",
}
for sk, ok in _raw_override_map.items():
    v = _ss(sk)
    if v is not None and v > 0:
        if sk == "raw_payout_pct":
            overrides["raw_payout_ratio"] = v / 100.0
        elif ok:
            overrides[ok] = v

# IV 子模型覆盖
iv_model_choice = _ss("iv_model_sel", "auto")
if iv_model_choice and iv_model_choice != "auto":
    overrides["iv_model_override"] = iv_model_choice.lower()

# ── 计算 ────────────────────────────────────────────────────────────────────
with st.spinner("拉取数据并计算中..."):
    try:
        from src.valmod.pipeline import run_valuation
        out = run_valuation(ticker, overrides)
    except Exception as e:
        st.error(str(e))
        st.stop()

if "error" in out:
    st.error(out["error"])
    st.stop()

# ── 全局变量 ─────────────────────────────────────────────────────────────────
_MODEL_LABELS = {
    "damodaran_pe": "PE 回归估值",
    "damodaran_iv": "内在价值折现",
    "ev_ebitda":    "EV/EBITDA 倍数法",
    "ev_sales":     "EV/Sales 倍数法",
}

r = out["final_range"]
p = out.get("current_price")
mid = r.get("mid")
recommended_model = out.get("recommended_model", "damodaran_pe")
recommended_reason = out.get("recommended_reason", "")
sector = out.get("sector") or "未知"
industry = out.get("industry") or ""
mo = out.get("model_outputs", {})
fin = out.get("financials", {})
norm_out = out.get("normalized", {})
industry_str = f" / {industry}" if industry else ""

# ── 1. 核心结果 ──────────────────────────────────────────────────────────────
st.subheader("估值结果")

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("当前股价", f"${p:.2f}" if p is not None else "N/A")
with c2:
    st.metric("估值中枢", f"${mid:.1f}" if mid else "N/A")
with c3:
    st.metric("估值区间", f"${r['low']:.1f} – ${r['high']:.1f}" if mid else "N/A")
with c4:
    if p and mid:
        diff = (mid - p) / p
        st.metric("中枢涨跌幅", f"{diff:+.1%}")
with c5:
    if r.get("divergence_alert"):
        st.warning("⚠ 相对估值与内在价值偏差 >20%，建议复核 WACC / 增长率")

# ── 推荐模型摘要 ─────────────────────────────────────────────────────────────
rec_label = _MODEL_LABELS.get(recommended_model, recommended_model)
_iv_val = mo.get("damodaran_iv")
_anchor_explain = (
    "**估值中枢 = 内在价值折现（模型三）**，模型二（相对估值）作置信区间验证。"
    if _iv_val is not None
    else "内在价值折现模型未运行（请填入侧边栏模型三参数 Rf/ERP），当前中枢为可用模型均值。"
)
st.info(
    f"**推荐估值模型：{rec_label}**　｜　行业：{sector}{industry_str}\n\n"
    f"{recommended_reason}\n\n"
    f"{_anchor_explain}　·　*情景分析见页面底部*"
)

# ─────────────────────────────────────────────────────────────────────────────
# ── 2. 各模型估值（新顺序：PE → 相对估值 → 内在价值）────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("各模型估值")

_t = tax_rate_pct / 100      # 税率（小数）
_rf = rf_pct / 100
_erp = erp_pct / 100
_g_stable = g_stable_iv_pct / 100


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模型一：PE 回归估值
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
dam_pe = mo.get("damodaran_pe")
dam_det = mo.get("damodaran_pe_details") or {}

with st.container(border=True):
    st.markdown("**模型一：PE 回归估值**（Damodaran 2025年1月回归方程）")

    # 公式
    st.code(
        "PE = 24.17 − 1.07 × β + 53.16 × gEPS + 1.08 × 派息率\n"
        "目标价 = PE × 稀释EPS\n"
        "β_levered = β_unlevered × [1 + (1 − t) × D/E]",
        language="",
    )

    col_params, col_results = st.columns([1, 1])

    with col_params:
        st.markdown("**参数一览**")

        # 侧边栏参数
        st.markdown(
            f"| 参数 | 数值 | 来源 |\n"
            f"|------|------|------|\n"
            f"| gEPS | **{gEPS_pct:.1f}%** | 侧边栏 |\n"
            f"| 行业无杠杆 β | **{sector_beta_unlevered:.2f}** | 侧边栏 |\n"
            f"| 税率 t | **{tax_rate_pct:.0f}%** | 侧边栏 |"
        )

        # 加杠杆后 Beta（计算结果）
        beta_used = dam_det.get("beta_used")
        beta_src = dam_det.get("beta_source", "")
        if beta_used is not None:
            st.markdown(
                f"| 参数 | 数值 | 来源 |\n"
                f"|------|------|------|\n"
                f"| 加杠杆后 β | **{beta_used:.3f}** | 自动推导 |"
            )

        # 派息率（财报）
        fin_payout = fin.get("payout_ratio")
        if fin_payout is not None:
            st.markdown(
                f"| 参数 | 数值 | 来源 |\n"
                f"|------|------|------|\n"
                f"| 派息率 | **{fin_payout:.1%}** | 财报读取 |"
            )
        else:
            st.markdown("⚠ **派息率** 未从财报读取到（若公司不派息，可视为 0%）")
            st.number_input(
                "补填：派息率（%）",
                min_value=0.0, max_value=100.0, value=0.0, step=0.5,
                format="%.1f",
                key="raw_payout_pct" + _sfx,
                help="填入后自动重算。0% = 无股息，正常适用于成长型公司。",
            )

        # 稀释 EPS（财报，最关键）
        fin_eps = fin.get("diluted_eps")
        if fin_eps is not None and fin_eps > 0:
            st.markdown(
                f"| 参数 | 数值 | 来源 |\n"
                f"|------|------|------|\n"
                f"| 稀释 EPS | **${fin_eps:.2f}** | 财报读取 |"
            )
        else:
            st.markdown("⚠ **稀释 EPS** 未读取到或为负（必须 > 0 才能计算目标价）")
            st.number_input(
                "补填：稀释 EPS（$/股）",
                min_value=0.01, max_value=1000.0, value=1.0, step=0.01,
                format="%.2f",
                key="raw_diluted_eps" + _sfx,
                help="来自年报 EPS（摊薄/稀释）。如 AAPL 2024 ≈ $6.08。",
            )

    with col_results:
        st.markdown("**计算结果**")
        if dam_pe is not None:
            st.metric(
                "目标价",
                f"${dam_pe:.1f}",
                delta=f"{(dam_pe - p) / p:+.1%}" if p else None,
            )
            d2, d3, d4 = st.columns(3)
            with d2:
                st.metric("隐含 PE", f"{dam_det.get('pe_implied', 0):.1f}x")
            with d3:
                st.metric("β（加杠杆）", f"{dam_det.get('beta_used', 0):.3f}")
            with d4:
                st.metric("派息率", f"{dam_det.get('payout_ratio', 0):.1%}")
            if dam_det.get("formula"):
                st.caption(f"公式验算：{dam_det['formula']}")
            if beta_src:
                st.caption(f"Beta来源：{beta_src}")
        else:
            st.warning("模型无法计算目标价")
            missing_hints = []
            if fin_eps is None or (fin_eps is not None and fin_eps <= 0):
                missing_hints.append("稀释EPS（请在左侧补填）")
            if beta_used is None:
                missing_hints.append("Beta（检查市值数据）")
            if missing_hints:
                st.caption("缺少：" + "、".join(missing_hints))
            err_msg = dam_det.get("note", dam_det.get("error", ""))
            if err_msg:
                st.caption(f"详情：{err_msg}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模型二：相对估值（基本面推导倍数）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
mult_det = mo.get("multiples_details") or {}
ev_ebitda_val = mo.get("ev_ebitda")
ev_sales_val = mo.get("ev_sales")
iv_anchor = mo.get("damodaran_iv")

# 判断 WACC 来源
if iv_anchor is not None:
    _wacc_source = "模型三（内在价值）推导"
elif rf_pct:
    _wacc_source = "Rf/ERP 参数计算"
else:
    _wacc_source = "默认回退值（10%）"

with st.container(border=True):
    st.markdown("**模型二：相对估值（基本面推导倍数 · 置信区间验证）**")
    st.caption("不作独立估值结论——与内在价值偏差 > 20% 时触发告警，提示复核假设。")

    # 公式
    st.code(
        "EV/EBIT = (1 − t) × (1 − RR) / (WACC − g)     ← EBIT ≈ EBITDA 近似\n"
        "EV/Sales = 税后EBIT利润率 × (1 − RR) × (1 + g) / (WACC − g)\n"
        "RR（再投资率）= max(CapEx − D&A, 0) / NOPAT",
        language="",
    )

    col_params2, col_results2 = st.columns([1, 1])

    with col_params2:
        st.markdown("**参数一览**")

        # WACC 及宏观参数
        wacc_used = mult_det.get("wacc_used")
        g_used = mult_det.get("g_used")
        rr_used = mult_det.get("reinvestment_rate")
        atm_used = mult_det.get("after_tax_margin")

        macro_lines = (
            f"| 参数 | 数值 | 来源 |\n"
            f"|------|------|------|\n"
        )
        if wacc_used is not None:
            macro_lines += f"| WACC / re | **{wacc_used:.2%}** | {_wacc_source} |\n"
        macro_lines += (
            f"| g (永续增长率) | **{g_stable_iv_pct:.1f}%** | 侧边栏 |\n"
            f"| 税率 t | **{tax_rate_pct:.0f}%** | 侧边栏 |"
        )
        st.markdown(macro_lines)

        if rr_used is not None:
            st.markdown(
                f"| 参数 | 数值 | 来源 |\n"
                f"|------|------|------|\n"
                f"| 再投资率 RR | **{rr_used:.1%}** | 自动推导 |\n"
                + (f"| 税后EBIT利润率 | **{atm_used:.1%}** | 自动推导 |" if atm_used is not None else "")
            )

        st.markdown("**财报数据**")

        # EBITDA
        fin_ebitda = fin.get("ebitda_b")
        if fin_ebitda is not None:
            st.markdown(f"• EBITDA：**${fin_ebitda:.1f}B** ← 财报")
        else:
            st.markdown("⚠ **EBITDA** 未读取到")
            st.number_input(
                "补填：EBITDA（$B）",
                min_value=0.1, value=10.0, step=0.5, format="%.1f",
                key="raw_ebitda_b" + _sfx,
            )

        # Revenue
        fin_rev = fin.get("revenue_b")
        if fin_rev is not None:
            st.markdown(f"• 营收：**${fin_rev:.1f}B** ← 财报")
        else:
            st.markdown("⚠ **营收** 未读取到")
            st.number_input(
                "补填：营收（$B）",
                min_value=0.1, value=50.0, step=1.0, format="%.1f",
                key="raw_revenue_b" + _sfx,
            )

        # EBIT
        fin_ebit = fin.get("operating_income_b")
        if fin_ebit is not None:
            st.markdown(f"• EBIT（营业利润）：**${fin_ebit:.1f}B** ← 财报")
        else:
            st.markdown("⚠ **EBIT（营业利润）** 未读取到")
            st.number_input(
                "补填：EBIT（$B）",
                min_value=0.0, value=5.0, step=0.5, format="%.1f",
                key="raw_operating_income_b" + _sfx,
            )

        # CapEx & D&A（显示，通常有数据）
        fin_capex = fin.get("capex_b")
        fin_da = fin.get("da_b")
        if fin_capex is not None:
            st.markdown(f"• CapEx：**${fin_capex:.1f}B** ← 财报")
        if fin_da is not None:
            st.markdown(f"• D&A：**${fin_da:.1f}B** ← 财报")

        # 净债务
        _net_debt_b = norm_out.get("net_debt")
        if _net_debt_b is not None:
            st.markdown(f"• 净债务：**${_net_debt_b / 1e9:.1f}B** ← 财报")

    with col_results2:
        st.markdown("**计算结果**")
        any_rel = False
        for label, key, mult_key in [
            ("EV/EBITDA 法", "ev_ebitda", "implied_ev_ebitda_mult"),
            ("EV/Sales 法",  "ev_sales",  "implied_ev_sales_mult"),
        ]:
            v = mo.get(key)
            mult_v = mult_det.get(mult_key)
            if v is not None:
                delta_str = f"{(v - p) / p:+.1%}" if p else None
                st.metric(label, f"${v:.1f}", delta=delta_str)
                if mult_v:
                    st.caption(f"隐含倍数：**{mult_v:.1f}×**")
                if iv_anchor and iv_anchor > 0:
                    dev = abs(v - iv_anchor) / iv_anchor
                    if dev > 0.20:
                        st.caption(
                            f"⚠ 与内在价值偏差 **{dev:.0%}**，建议复核 WACC"
                            f"（{mult_det.get('wacc_used', 0):.2%}）或 g"
                        )
                any_rel = True

        if not any_rel:
            st.warning("相对估值不可用")
            missing_rel = []
            if fin.get("ebitda_b") is None:
                missing_rel.append("EBITDA（请补填）")
            if fin.get("revenue_b") is None:
                missing_rel.append("营收（请补填）")
            if missing_rel:
                st.caption("缺少：" + "、".join(missing_rel))

        if wacc_used:
            st.caption(
                f"推导参数：WACC={wacc_used:.2%}  g={g_used:.2%}"
                + (f"  再投资率={rr_used:.1%}" if rr_used is not None else "")
                + (f"  税后EBIT利润率={atm_used:.1%}" if atm_used is not None else "")
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模型三：内在价值折现（FCFF / FCFE / DDM）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
iv_val = mo.get("damodaran_iv")
iv_det = mo.get("damodaran_iv_details") or {}
_IV_MODEL_NAMES = {
    "fcff": "FCFF（公司自由现金流）",
    "fcfe": "FCFE（股权自由现金流）",
    "ddm":  "DDM（股利贴现）",
}
iv_model_used = iv_det.get("model_used", "").lower()
iv_model_label = _IV_MODEL_NAMES.get(iv_model_used, iv_model_used.upper() or "未运行")
auto_model = iv_det.get("auto_model", iv_model_used)
is_manual_override = iv_det.get("is_manual_override", False)

with st.container(border=True):
    st.markdown("**模型三：内在价值折现**（估值中枢锚点）")

    # ── 子模型选择器（radio） ──────────────────────────────────────────────
    _auto_label = f"自动推荐（{auto_model.upper()}）" if auto_model else "自动推荐"
    _iv_radio_opts = ["auto", "FCFF", "FCFE", "DDM"]
    _iv_radio_labels = {
        "auto":  _auto_label,
        "FCFF":  "FCFF — 公司自由现金流",
        "FCFE":  "FCFE — 股权自由现金流",
        "DDM":   "DDM — 股利贴现",
    }
    st.radio(
        "折现子模型",
        options=_iv_radio_opts,
        format_func=lambda x: _iv_radio_labels[x],
        horizontal=True,
        key="iv_model_sel" + _sfx,
        help=(
            "**自动推荐**：系统依据财务特征自动选择最适合的子模型\n\n"
            "• DDM：派息率>70% 且 债/市值<50% → 成熟现金奶牛\n"
            "• FCFF：亏损 或 债/市值>80% → 高杠杆/亏损公司\n"
            "• FCFE：其余情况 → 杠杆稳定且盈利的一般企业\n\n"
            "可手动切换对比不同子模型的估值差异。"
        ),
    )

    # ── 公式（按当前子模型显示）──────────────────────────────────────────────
    if iv_model_used == "fcff":
        st.code(
            "FCFF = EBIT × (1−t) − Net CapEx − ΔNon-cash WC\n"
            "WACC = re × E/(D+E) + rd × (1−t) × D/(D+E)\n"
            "re = Rf + β × ERP  ，  rd = Rf + 违约利差\n"
            "TV = FCFF_n × (1+g_stable) / (WACC − g_stable)\n"
            "每股价值 = (EV − 总债务 + 现金) / 稀释股本",
            language="",
        )
    elif iv_model_used == "fcfe":
        st.code(
            "FCFE = 净利润 + D&A − CapEx − ΔWC + 净债务融资额\n"
            "re = Rf + β × ERP\n"
            "TV = FCFE_n × (1+g_stable) / (re − g_stable)\n"
            "每股价值 = PV(FCFE高速增长期) + PV(TV)",
            language="",
        )
    elif iv_model_used == "ddm":
        st.code(
            "DPS₀ = 已付股息 / 股本  或  稀释EPS × 派息率\n"
            "re = Rf + β × ERP\n"
            "TV = DPS_n × (1+g_stable) / (re − g_stable)  [约束：g_stable ≤ Rf]\n"
            "每股价值 = Σ DPS_t/(1+re)^t + TV/(1+re)^n",
            language="",
        )
    else:
        st.caption("请填写侧边栏中的 Rf / ERP 等参数，启动内在价值折现模型。")

    col_p3, col_r3 = st.columns([1, 1])

    with col_p3:
        # ── 宏观参数（来自侧边栏）──────────────────────────────────────────
        st.markdown("**宏观参数（侧边栏）**")
        macro3 = (
            f"| 参数 | 数值 |\n"
            f"|------|------|\n"
            f"| Rf（无风险利率）| **{rf_pct:.1f}%** |\n"
            f"| ERP（股权风险溢价）| **{erp_pct:.1f}%** |\n"
            f"| 行业无杠杆 β | **{sector_beta_unlevered:.2f}** |\n"
            f"| 高速增长率 g_high | **{g_high_iv_pct:.1f}%** |\n"
            f"| 高速增长年数 n | **{int(n_high_iv)} 年** |\n"
            f"| 永续增长率 g_stable | **{g_stable_iv_pct:.1f}%**（≤ Rf 约束）|"
        )
        if iv_model_used == "fcff":
            macro3 += f"\n| 违约利差 | **{default_spread_pct:.1f}%** |"
        st.markdown(macro3)

        # ── 财报数据（按子模型展示不同字段）───────────────────────────────
        st.markdown("**财报数据**")

        def _show_or_input(label, fin_key, ss_key, unit="$B", min_v=0.0, default_v=10.0, step=0.5, fmt="%.1f"):
            val = fin.get(fin_key)
            if val is not None and val > 0:
                st.markdown(f"• {label}：**${val:.2f}B** ← 财报")
            else:
                st.markdown(f"⚠ **{label}** 未读取到")
                st.number_input(
                    f"补填：{label}（{unit}）",
                    min_value=min_v, value=default_v, step=step, format=fmt,
                    key=ss_key + _sfx,
                )

        def _show_val_optional(label, fin_key, unit="$B", allow_zero=False):
            """显示数值（允许 None 或 0，不要求用户补填）。"""
            val = fin.get(fin_key)
            if val is not None:
                st.markdown(f"• {label}：**${val:.2f}B** ← 财报")
            else:
                st.markdown(f"• {label}：— 未读取（按 0 处理）")

        if iv_model_used == "fcff":
            _show_or_input("EBIT（营业利润）", "operating_income_b", "raw_operating_income_b", min_v=0.01)
            _show_or_input("CapEx", "capex_b", "raw_capex_b", default_v=5.0)
            _show_or_input("D&A（折旧摊销）", "da_b", "raw_da_b", default_v=3.0)
            _show_or_input("总债务", "total_debt_b", "raw_total_debt_b", default_v=50.0)
            _show_or_input("现金及等价物", "cash_b", "raw_cash_b", default_v=20.0)
            _show_or_input("稀释股本", "shares_b", "raw_shares_b", unit="B股", default_v=1.0)
            _show_val_optional("营运资本变动（ΔWC）", "working_capital_b", allow_zero=True)

        elif iv_model_used == "fcfe":
            _show_or_input("净利润", "net_income_b", "raw_net_income_b", min_v=0.01)
            _show_or_input("D&A（折旧摊销）", "da_b", "raw_da_b", default_v=3.0)
            _show_or_input("CapEx", "capex_b", "raw_capex_b", default_v=5.0)
            _show_or_input("稀释股本", "shares_b", "raw_shares_b", unit="B股", default_v=1.0)
            # 净债务融资额（可为负，允许 0）
            fin_ndi = fin.get("net_debt_issuance_b")
            if fin_ndi is not None:
                st.markdown(f"• 净债务融资额：**${fin_ndi:.2f}B** ← 财报（负=还债）")
            else:
                st.markdown("• 净债务融资额：— 未读取（按 0 处理）")
                st.number_input(
                    "补填：净债务融资额（$B）",
                    min_value=-200.0, max_value=200.0, value=0.0, step=1.0, format="%.1f",
                    key="raw_net_debt_issuance_b" + _sfx,
                    help="净新增借债（借入-偿还）。正=新增借债，负=净还债。",
                )

        elif iv_model_used == "ddm":
            fin_div = fin.get("dividends_paid_b")
            fin_eps = fin.get("diluted_eps")
            fin_payout = fin.get("payout_ratio")
            if fin_div is not None and fin_div > 0:
                st.markdown(f"• 已付股息总额：**${fin_div:.2f}B** ← 财报")
            elif fin_eps and fin_eps > 0 and fin_payout:
                st.markdown(f"• DPS₀ 由 EPS(${fin_eps:.2f}) × 派息率({fin_payout:.1%}) 估算")
            else:
                st.markdown("⚠ **股息数据（已付股息 / DPS）** 未读取到")
                st.number_input(
                    "补填：已付股息总额（$B）",
                    min_value=0.0, value=1.0, step=0.1, format="%.2f",
                    key="raw_dividends_paid_b" + _sfx,
                )
            _show_or_input("稀释股本", "shares_b", "raw_shares_b", unit="B股", default_v=1.0)

    with col_r3:
        st.markdown("**计算结果**")
        if iv_val is not None:
            st.metric(
                "目标价",
                f"${iv_val:.1f}",
                delta=f"{(iv_val - p) / p:+.1%}" if p else None,
            )
            r3a, r3b = st.columns(2)
            with r3a:
                if iv_model_used == "fcff":
                    st.metric("WACC", f"{iv_det.get('wacc', 0):.2%}")
                else:
                    st.metric("股权成本 re", f"{iv_det.get('re', 0):.2%}")
            with r3b:
                st.metric("加杠杆 β", f"{iv_det.get('beta_levered', 0):.3f}")

            tp = iv_det.get("terminal_pct")
            color_iv = "🔴" if tp and tp > 0.70 else "🟡" if tp and tp > 0.55 else "🟢"
            st.metric("终值占比", f"{color_iv} {tp:.0%}" if tp is not None else "N/A")

            # 现金流明细
            if iv_model_used == "fcff" and iv_det.get("fcff_0_B") is not None:
                st.caption(
                    f"FCFF₀ = ${iv_det['fcff_0_B']:.2f}B  "
                    f"净CapEx = ${iv_det.get('net_capex_B', 0):.2f}B  "
                    f"权益价值 = ${iv_det.get('equity_value_B', 0):.1f}B"
                )
            elif iv_model_used == "fcfe" and iv_det.get("fcfe_0_B") is not None:
                st.caption(
                    f"FCFE₀ = ${iv_det['fcfe_0_B']:.2f}B  "
                    f"净利润 = ${iv_det.get('net_income_B', 0):.2f}B"
                )
            elif iv_model_used == "ddm" and iv_det.get("dps_0") is not None:
                st.caption(
                    f"DPS₀ = ${iv_det['dps_0']:.2f}/股  "
                    f"来源：{iv_det.get('dps_source', '')}"
                )

            st.caption(
                f"g_stable = {iv_det.get('g_stable_used', 0):.2%}  ｜  "
                f"{'手动指定' if is_manual_override else '自动选择'} {iv_model_used.upper()}\n\n"
                f"{iv_det.get('selection_reason', '')}"
            )
        else:
            err = iv_det.get("error", "参数不足（请填入侧边栏 Rf/ERP 等参数）")
            st.warning(f"模型不可用：{err}")


# ── 3. 告警 ──────────────────────────────────────────────────────────────────
alerts = out.get("alerts", [])
if alerts:
    st.subheader("告警")
    for a in alerts:
        msg = a.get("message", "")
        reason = a.get("reason", "")
        suggestion = a.get("suggestion", "")
        detail = f"　原因：{reason}" + (f"　建议：{suggestion}" if suggestion else "")
        if a.get("level") == "critical":
            st.error(f"🔴 {msg}{detail}")
        else:
            st.warning(f"🟡 {msg}{detail}")

# ── 4. 数据质量 ──────────────────────────────────────────────────────────────
with st.expander("数据质量"):
    dq = out.get("data_quality", {})
    st.write(f"完整度：{dq.get('completeness', 0):.0%}")
    if dq.get("missing"):
        st.caption("缺失字段：" + "、".join(dq["missing"]))
    if dq.get("critical"):
        for c in dq["critical"]:
            st.error(c)
    if dq.get("warnings"):
        for w in dq["warnings"]:
            st.warning(w)

# ── 5. 完整 JSON（调试用）───────────────────────────────────────────────────
with st.expander("完整数据（调试用）"):
    st.json(out)

# ── 6. 情景分析（底部，基于推荐模型）────────────────────────────────────────
st.markdown("---")
st.subheader("情景分析")

mo_sc = out.get("model_outputs", {})
norm_sc = out.get("normalized", {})
rec_label_sc = _MODEL_LABELS.get(recommended_model, recommended_model)

st.markdown(
    f"**推荐模型：{rec_label_sc}**　｜　行业：{sector}{industry_str}\n\n"
    f"以下在 **{rec_label_sc}** 的基础上，通过调整关键参数生成悲观 / 基准 / 乐观三个情景。"
)

# ----- PE 回归情景 -----
if recommended_model == "damodaran_pe":
    dam_det_sc = mo_sc.get("damodaran_pe_details") or {}
    beta_sc = dam_det_sc.get("beta_used")
    payout_sc = dam_det_sc.get("payout_ratio", 0.0)
    eps_sc = dam_det_sc.get("diluted_eps")
    _INT, _B_c, _G, _P = 24.17, -1.07, 53.16, 1.08

    def _dam_price(gEPS):
        if beta_sc is None or not eps_sc or eps_sc <= 0:
            return None
        pe = _INT + _B_c * beta_sc + _G * gEPS + _P * payout_sc
        return pe * eps_sc if pe > 0 else None

    gEPS_def = gEPS_pct / 100
    _beta_str = f"{beta_sc:.3f}" if beta_sc is not None else "N/A"
    _eps_str = f"{eps_sc:.2f}" if eps_sc else "N/A"
    st.caption(f"调整变量：**预期EPS增速 gEPS**（β={_beta_str}，派息率={payout_sc:.1%}，稀释EPS=${_eps_str}）")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_g = st.number_input("Bear gEPS（%）", value=round((gEPS_def - 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_bear_g") / 100
    with sc2:
        base_g = st.number_input("Base gEPS（%）", value=round(gEPS_def * 100, 1), step=0.5, format="%.1f", key="sc_base_g") / 100
    with sc3:
        bull_g = st.number_input("Bull gEPS（%）", value=round((gEPS_def + 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_bull_g") / 100
    sc_prices = [(_dam_price(bear_g), "悲观 Bear", "#EF4444"), (_dam_price(base_g), "基准 Base", "#F59E0B"), (_dam_price(bull_g), "乐观 Bull", "#22C55E")]

# ----- 内在价值折现情景 -----
elif recommended_model == "damodaran_iv":
    iv_det_sc = mo_sc.get("damodaran_iv_details") or {}
    iv_model_sc = iv_det_sc.get("model_used", "").lower()
    re_sc = iv_det_sc.get("re", 0.10)
    wacc_sc = iv_det_sc.get("wacc", re_sc)
    g_stable_sc = iv_det_sc.get("g_stable_used", 0.025)

    st.caption(f"调整变量：**高速增长率 g_high**（模型={iv_model_sc.upper()}，折现率={wacc_sc if iv_model_sc == 'fcff' else re_sc:.2%}，g_stable={g_stable_sc:.2%}）")

    g_high_def = g_high_iv_pct / 100
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_gh = st.number_input("Bear g_high（%）", value=round((g_high_def - 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_iv_bear") / 100
    with sc2:
        base_gh = st.number_input("Base g_high（%）", value=round(g_high_def * 100, 1), step=0.5, format="%.1f", key="sc_iv_base") / 100
    with sc3:
        bull_gh = st.number_input("Bull g_high（%）", value=round((g_high_def + 0.05) * 100, 1), step=0.5, format="%.1f", key="sc_iv_bull") / 100

    def _iv_approx(g_high_new):
        if iv_val is None or g_high_def == 0:
            return None
        ratio = (1 + g_high_new) / (1 + g_high_def)
        return iv_val * ratio

    sc_prices = [
        (_iv_approx(bear_gh), "悲观 Bear", "#EF4444"),
        (_iv_approx(base_gh), "基准 Base", "#F59E0B"),
        (_iv_approx(bull_gh), "乐观 Bull", "#22C55E"),
    ]

# ----- EV/EBITDA 情景 -----
elif recommended_model == "ev_ebitda":
    ebitda_sc = norm_sc.get("ebitda")
    nd_sc = norm_sc.get("net_debt", 0) or 0
    sh_sc = norm_sc.get("shares_diluted")

    def _eveb_price(anchor):
        if not ebitda_sc or not sh_sc or ebitda_sc <= 0 or sh_sc <= 0:
            return None
        eq = anchor * ebitda_sc - nd_sc
        return eq / sh_sc if eq > 0 else None

    st.caption(f"调整变量：**EV/EBITDA 倍数**（EBITDA=${ebitda_sc / 1e9:.2f}B，净债务=${nd_sc / 1e9:.2f}B）" if ebitda_sc else "EV/EBITDA 数据不可用")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_anch = st.number_input("Bear EV/EBITDA（×）", value=10.0, step=0.5, format="%.1f", key="sc_bear_ev")
    with sc2:
        base_anch = st.number_input("Base EV/EBITDA（×）", value=12.0, step=0.5, format="%.1f", key="sc_base_ev")
    with sc3:
        bull_anch = st.number_input("Bull EV/EBITDA（×）", value=14.0, step=0.5, format="%.1f", key="sc_bull_ev")
    sc_prices = [(_eveb_price(bear_anch), "悲观 Bear", "#EF4444"), (_eveb_price(base_anch), "基准 Base", "#F59E0B"), (_eveb_price(bull_anch), "乐观 Bull", "#22C55E")]

# ----- EV/Sales 情景 -----
else:
    rev_sc = norm_sc.get("revenue")
    nd_sc = norm_sc.get("net_debt", 0) or 0
    sh_sc = norm_sc.get("shares_diluted")

    def _evs_price(anchor):
        if not rev_sc or not sh_sc or rev_sc <= 0 or sh_sc <= 0:
            return None
        eq = anchor * rev_sc - nd_sc
        return eq / sh_sc if eq > 0 else None

    st.caption(f"调整变量：**EV/Sales 倍数**（Revenue=${rev_sc / 1e9:.2f}B，净债务=${nd_sc / 1e9:.2f}B）" if rev_sc else "EV/Sales 数据不可用")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        bear_anch = st.number_input("Bear EV/Sales（×）", value=3.0, step=0.5, format="%.1f", key="sc_bear_evs")
    with sc2:
        base_anch = st.number_input("Base EV/Sales（×）", value=5.0, step=0.5, format="%.1f", key="sc_base_evs")
    with sc3:
        bull_anch = st.number_input("Bull EV/Sales（×）", value=7.0, step=0.5, format="%.1f", key="sc_bull_evs")
    sc_prices = [(_evs_price(bear_anch), "悲观 Bear", "#EF4444"), (_evs_price(base_anch), "基准 Base", "#F59E0B"), (_evs_price(bull_anch), "乐观 Bull", "#22C55E")]

# ----- 情景结果展示 -----
valid_sc = [(v, lab, col) for v, lab, col in sc_prices if v is not None]
if valid_sc:
    m1, m2, m3 = st.columns(3)
    for col_obj, (v, lab, _) in zip([m1, m2, m3], sc_prices):
        with col_obj:
            if v is not None:
                delta = f"{(v - p) / p:+.1%}" if p else None
                st.metric(lab, f"${v:.1f}", delta=delta)
            else:
                st.metric(lab, "N/A")

    fig_sc2 = go.Figure()
    for v, lab, col in sc_prices:
        if v is not None:
            fig_sc2.add_trace(go.Bar(name=lab.split()[1], x=[lab.split()[1]], y=[v], marker_color=col, width=0.4))
    if p:
        fig_sc2.add_hline(y=p, line_dash="dash", line_color="white",
                          annotation_text=f"当前股价 ${p:.1f}", annotation_position="top left")
    fig_sc2.update_layout(
        height=320, showlegend=False, margin=dict(l=20, r=20, t=40, b=20),
        yaxis_title="估值（$）",
        title=f"三情景估值 vs 当前股价（{rec_label_sc}）",
    )
    st.plotly_chart(fig_sc2, use_container_width=True)
else:
    st.warning("情景分析所需数据不足，请检查数据质量或切换模型。")

# ── 7. 格言 ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    """
<div style="text-align: center; color: #888; font-size: 0.85em; line-height: 2.2em; padding: 12px 0 4px 0;">

善战者无赫赫之功 ——《孙子兵法》<br>
<em>The supreme warrior wins without celebrated feats. — Sun Tzu</em>

<br>

做一个战争型而不是战斗型的选手，我们不需要每天都有新主意，需要关心的是如何将一个正确的主意数年如一日地做好，"不抛弃，不放弃"是真的大不易。——杨天南<br>
<em>Be a strategist, not just a fighter. We don't need a new idea every day — what matters is executing one right idea with unwavering consistency for years. To never abandon, never give up, is truly no small feat. — Yang Tiannan</em>

<br>

价值投资者的悲哀在于，即便他们以价值作为行为方式的前提，他们的记分牌却是价格。——杨天南<br>
<em>The tragedy of value investors is that, even though they take value as the premise of their actions, their scorecard is price. — Yang Tiannan</em>

</div>
""",
    unsafe_allow_html=True,
)
