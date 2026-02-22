# =============================================================================
# 估值系统 - 数据结构定义（types.py）
# =============================================================================
# 本文件定义整个估值流水线中所有「数据容器」的模板。
# 你不需要改代码逻辑，只需通过「人类语言」理解每个字段含义，
# 并在 config/analyst_overrides.yaml 或 Streamlit 侧边栏调整参数即可。
#
# 各层数据流：RawData → NormalizedFinancials → Assumptions → ModelOutputs → FinalRange
# =============================================================================

from dataclasses import dataclass, field
from typing import Optional, Any


# -----------------------------------------------------------------------------
# Layer 1 输出：原始数据（从 Yahoo Finance 拉取，未经处理）
# -----------------------------------------------------------------------------
@dataclass
class RawData:
    """
    原始数据容器。来源：yfinance.Ticker(ticker).info 及财报表。
    字段缺失时为 None，不做插补。
    """
    ticker: str
    # 市场数据
    current_price: Optional[float] = None      # 当前股价
    market_cap: Optional[float] = None       # 市值
    shares: Optional[float] = None            # 股本（优先稀释股本，与 MOOMOO 等一致）
    enterprise_value: Optional[float] = None  # 企业价值 EV
    # 估值字段（yfinance 的 PE 为未稀释，仅作参考；本系统会自行计算稀释 PE）
    trailing_pe: Optional[float] = None       #  trailing PE（未稀释，不可靠）
    forward_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    ebitda: Optional[float] = None
    # 财报核心项（年度优先）
    revenue: Optional[float] = None          # 收入
    net_income: Optional[float] = None       # 净利润
    cfo: Optional[float] = None             # 经营现金流（CFO）
    capex: Optional[float] = None           # 资本开支（若缺失可用 PPE 变化估算）
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    # 稀释 EPS（用于计算稀释 PE，与 MOOMOO 一致）
    diluted_eps: Optional[float] = None
    # 折旧摊销（用于激进会计检测）
    depreciation_amortization: Optional[float] = None
    # PPE 净额（用于 CAPEX 缺失时估算：PPE 年度变化）
    ppe_net: Optional[float] = None
    ppe_net_prior: Optional[float] = None
    # Damodaran PE 所需字段
    beta: Optional[float] = None                  # yfinance 回归 Beta（作为备用）
    payout_ratio: Optional[float] = None          # 派息率 = 股息 / 净利润
    # 行业信息（用于模型推荐）
    sector: Optional[str] = None                  # yfinance 行业分类，如 "Technology"
    industry: Optional[str] = None                # yfinance 细分行业
    # 达莫达兰内在价值模型所需字段
    operating_income: Optional[float] = None      # EBIT（营业利润）
    working_capital: Optional[float] = None       # 流动资产 - 流动负债（当年）
    working_capital_prior: Optional[float] = None # 上一年营运资本（用于计算 ΔWC）
    net_debt_issuance: Optional[float] = None     # 净债务融资额（正=借入，负=偿还）
    dividends_paid: Optional[float] = None        # 已支付股息总额（绝对值，正数）
    # 财报最新日期（用于时效性检查）
    latest_financial_date: Optional[str] = None
    # 拉取时间戳
    fetch_timestamp: Optional[str] = None


# -----------------------------------------------------------------------------
# Layer 1 输出：数据质量报告
# -----------------------------------------------------------------------------
@dataclass
class DataQualityReport:
    """
    数据质量报告。用于展示缺失项、异常项、逻辑自洽性、时效性。
    """
    completeness: float = 0.0   # 完整度 0~1
    missing: list = field(default_factory=list)   # 缺失字段清单
    warnings: list = field(default_factory=list)  # 警告（如 CAPEX 估算、股本反推）
    critical: list = field(default_factory=list)  # 严重问题（如 CFO 缺失导致 DCF 不可用）
    source_log: str = ""       # 数据来源、拉取时间


# -----------------------------------------------------------------------------
# Layer 2 输出：标准化财务数据（可估值形式）
# -----------------------------------------------------------------------------
@dataclass
class NormalizedFinancials:
    """
    标准化后的财务数据。用于 DCF、相对估值等模型输入。
    所有派生项（FCF、净债务等）在此计算；若为估算会记录在 transform_log 中。
    """
    ticker: str
    # 核心派生项
    fcf: Optional[float] = None              # 自由现金流 = CFO - CAPEX
    net_debt: Optional[float] = None         # 净债务 = Total Debt - Cash
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    # 比率（能算则算）
    fcf_margin: Optional[float] = None     # FCF / Revenue
    ebitda_margin: Optional[float] = None   # EBITDA / Revenue
    roe: Optional[float] = None             # 净资产收益率
    # 股本（优先稀释，用于每股估值）
    shares_diluted: Optional[float] = None
    # 口径说明
    period_type: str = "annual"              # annual / quarterly
    # 估算与变换日志（供你核对）
    transform_log: list = field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 3 输出：模型选择结果
# -----------------------------------------------------------------------------
@dataclass
class SelectionResult:
    """根据数据可得性选择的可用模型及理由。"""
    enabled_models: list = field(default_factory=list)  # 如 ["dcf", "ev_ebitda"]
    rationale: str = ""                     # 选择理由（人类可读）
    company_tag: str = ""                   # 如 "fcf_positive" / "revenue_only"
    recommended_model: str = "damodaran_pe" # 根据行业推荐的首选模型
    recommended_reason: str = ""            # 推荐理由（人类可读）


# -----------------------------------------------------------------------------
# Layer 4 输出：估值假设（所有参数可覆盖，并记录来源）
# [ANALYST_REQUIRED] 标注的为需要分析师重点核对的参数
# -----------------------------------------------------------------------------
@dataclass
class Assumptions:
    """
    估值假设。默认值见下方；可通过 overrides 或 config 覆盖。
    """
    # [ANALYST_REQUIRED] 折现率 r：通常 8%~12%，高成长可略低，高风险可略高
    discount_rate: float = 0.10
    # [ANALYST_REQUIRED] 永续增长 g：不宜超过名义 GDP，通常 2%~3%
    perpetual_growth: float = 0.025
    explicit_years: int = 5                 # 显式预测年数
    # [ANALYST_REQUIRED] 显式期增长率：优先用历史 CAGR，算不出则用默认 5%
    explicit_growth_rate: float = 0.05
    # 假设来源记录（default / user）
    assumption_log: list = field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 5 输出：各模型估值结果
# -----------------------------------------------------------------------------
@dataclass
class ModelOutputs:
    """各估值模型的输出。能算则填，不能则 None。"""
    ev_ebitda: Optional[float] = None
    ev_sales: Optional[float] = None
    multiples_details: Optional[dict] = None      # 倍数推导明细（implied倍数、WACC、再投资率等）
    # Damodaran PE 估值
    damodaran_pe: Optional[float] = None          # 目标价
    damodaran_pe_details: Optional[dict] = None   # 计算明细（beta/payout/gEPS/PE倍数）
    # 达莫达兰内在价值模型（FCFF / FCFE / DDM）
    damodaran_iv: Optional[float] = None          # 内在价值每股估值
    damodaran_iv_details: Optional[dict] = None   # 含 model_used, wacc/re, terminal_pct 等
    # 各模型内部警告
    model_warnings: list = field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 6 输出：三情景区间
# -----------------------------------------------------------------------------
@dataclass
class ScenarioOutputs:
    """Bear / Base / Bull 三情景 + 敏感性表。"""
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    sensitivity: dict = field(default_factory=dict)  # 单变量敏感性


# -----------------------------------------------------------------------------
# Layer 7 输出：最终估值区间
# -----------------------------------------------------------------------------
@dataclass
class FinalRange:
    """融合后的最终估值区间。"""
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    model_contributions: dict = field(default_factory=dict)  # 各模型贡献
    weight_explain: str = ""                # 权重说明
    divergence_alert: bool = False          # 模型分歧 >30% 时 True


# -----------------------------------------------------------------------------
# Layer 8 输出：告警列表
# -----------------------------------------------------------------------------
@dataclass
class AlertItem:
    """单条告警。"""
    level: str          # "critical" / "warning"
    message: str
    reason: str
    affected_models: list = field(default_factory=list)
    suggestion: str = ""
