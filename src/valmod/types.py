# =============================================================================
# Valuation System - Data Structure Definitions (types.py)
# =============================================================================
# This file defines all "data container" templates used throughout the valuation
# pipeline. You do not need to modify any logic here — simply understand each
# field's meaning and adjust parameters via config/analyst_overrides.yaml or
# the Streamlit sidebar.
#
# Data flow across layers:
#   RawData → NormalizedFinancials → Assumptions → ModelOutputs → FinalRange
# =============================================================================

from dataclasses import dataclass, field
from typing import Optional, Any


# -----------------------------------------------------------------------------
# Layer 1 output: raw data (fetched from Yahoo Finance, unprocessed)
# -----------------------------------------------------------------------------
@dataclass
class RawData:
    """
    Raw data container. Source: yfinance.Ticker(ticker).info and financial statements.
    Missing fields are None; no imputation is performed here.
    """
    ticker: str
    # Market data
    current_price: Optional[float] = None      # Current stock price
    market_cap: Optional[float] = None         # Market capitalization
    shares: Optional[float] = None             # Shares outstanding (prefer diluted, consistent with MOOMOO etc.)
    enterprise_value: Optional[float] = None   # Enterprise value (EV)
    # Valuation fields (yfinance PE is undiluted — for reference only; system computes diluted PE independently)
    trailing_pe: Optional[float] = None        # Trailing PE (undiluted, unreliable)
    forward_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    ebitda: Optional[float] = None
    # Core income statement items (annual preferred)
    revenue: Optional[float] = None            # Total revenue
    net_income: Optional[float] = None         # Net income
    cfo: Optional[float] = None                # Cash flow from operations (CFO)
    capex: Optional[float] = None              # Capital expenditure (estimated from PPE change if missing)
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    # Diluted EPS (used to compute diluted PE, consistent with MOOMOO)
    diluted_eps: Optional[float] = None
    # Depreciation & amortization (used for aggressive accounting detection)
    depreciation_amortization: Optional[float] = None
    # Net PP&E (used to estimate CapEx from annual change when CapEx is missing)
    ppe_net: Optional[float] = None
    ppe_net_prior: Optional[float] = None
    # Fields required by the Damodaran PE regression
    beta: Optional[float] = None                  # yfinance regression beta (fallback)
    payout_ratio: Optional[float] = None          # Payout ratio = dividends / net income
    # Sector info (used for model recommendation)
    sector: Optional[str] = None                  # yfinance sector classification, e.g. "Technology"
    industry: Optional[str] = None                # yfinance sub-industry
    # Fields required by the Damodaran intrinsic value models
    operating_income: Optional[float] = None      # EBIT (operating income)
    working_capital: Optional[float] = None       # Current assets - current liabilities (current year)
    working_capital_prior: Optional[float] = None # Prior year working capital (used to compute ΔWC)
    net_debt_issuance: Optional[float] = None     # Net debt issuance (positive = new borrowing, negative = repayment)
    dividends_paid: Optional[float] = None        # Total dividends paid (absolute value, positive)
    # Latest financial date (used for data freshness check)
    latest_financial_date: Optional[str] = None
    # Fetch timestamp
    fetch_timestamp: Optional[str] = None


# -----------------------------------------------------------------------------
# Layer 1 output: data quality report
# -----------------------------------------------------------------------------
@dataclass
class DataQualityReport:
    """
    Data quality report. Surfaces missing fields, anomalies, logical consistency, and data freshness.
    """
    completeness: float = 0.0   # Completeness score 0–1
    missing: list = field(default_factory=list)   # List of missing fields
    warnings: list = field(default_factory=list)  # Warnings (e.g. CapEx estimated, shares back-calculated)
    critical: list = field(default_factory=list)  # Critical issues (e.g. CFO missing → DCF unavailable)
    source_log: str = ""        # Data source and fetch timestamp


# -----------------------------------------------------------------------------
# Layer 2 output: normalized financials (ready for valuation models)
# -----------------------------------------------------------------------------
@dataclass
class NormalizedFinancials:
    """
    Normalized financial data. Used as input for DCF, relative valuation, and other models.
    All derived items (FCF, net debt, etc.) are computed here; estimates are recorded in transform_log.
    """
    ticker: str
    # Core derived items
    fcf: Optional[float] = None              # Free cash flow = CFO - CapEx
    net_debt: Optional[float] = None         # Net debt = Total Debt - Cash
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    # Ratios (computed when data is available)
    fcf_margin: Optional[float] = None       # FCF / Revenue
    ebitda_margin: Optional[float] = None    # EBITDA / Revenue
    roe: Optional[float] = None              # Return on equity
    # Shares (prefer diluted, used for per-share valuation)
    shares_diluted: Optional[float] = None
    # Period type
    period_type: str = "annual"              # annual / quarterly
    # Transformation log (for review)
    transform_log: list = field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 3 output: model selection result
# -----------------------------------------------------------------------------
@dataclass
class SelectionResult:
    """Model selection based on data availability, with sector-based recommendation."""
    enabled_models: list = field(default_factory=list)  # e.g. ["ev_ebitda", "ev_sales"]
    rationale: str = ""                      # Human-readable selection rationale
    company_tag: str = ""                    # e.g. "fcf_positive" / "revenue_only"
    recommended_model: str = "damodaran_pe"  # Sector-driven preferred model
    recommended_reason: str = ""             # Human-readable recommendation reason


# -----------------------------------------------------------------------------
# Layer 4 output: valuation assumptions (all parameters can be overridden with source logging)
# [ANALYST_REQUIRED] fields are the ones analysts must review carefully
# -----------------------------------------------------------------------------
@dataclass
class Assumptions:
    """
    Valuation assumptions. Defaults shown below; can be overridden via overrides dict or config.
    """
    # [ANALYST_REQUIRED] Discount rate r: typically 8%–12%; slightly lower for high-growth, higher for high-risk
    discount_rate: float = 0.10
    # [ANALYST_REQUIRED] Perpetual growth g: should not exceed nominal GDP; typically 2%–3%
    perpetual_growth: float = 0.025
    explicit_years: int = 5                  # Number of explicit forecast years
    # [ANALYST_REQUIRED] Explicit period growth rate: uses historical CAGR if available, else defaults to 5%
    explicit_growth_rate: float = 0.05
    # Log of assumption sources (default / user)
    assumption_log: list = field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 5 output: model valuation results
# -----------------------------------------------------------------------------
@dataclass
class ModelOutputs:
    """Outputs from each valuation model. Filled when computable, None otherwise."""
    ev_ebitda: Optional[float] = None
    ev_sales: Optional[float] = None
    multiples_details: Optional[dict] = None      # Multiple derivation detail (implied multiple, WACC, reinvestment rate, etc.)
    # Damodaran PE regression
    damodaran_pe: Optional[float] = None          # Target price
    damodaran_pe_details: Optional[dict] = None   # Computation detail (beta / payout / gEPS / PE multiple)
    # Damodaran intrinsic value model (FCFF / FCFE / DDM)
    damodaran_iv: Optional[float] = None          # Intrinsic value per share
    damodaran_iv_details: Optional[dict] = None   # Contains model_used, wacc/re, terminal_pct, etc.
    # Per-model internal warnings
    model_warnings: list = field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 6 output: three-scenario range
# -----------------------------------------------------------------------------
@dataclass
class ScenarioOutputs:
    """Bear / Base / Bull three-scenario outputs + sensitivity table."""
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    sensitivity: dict = field(default_factory=dict)  # Single-variable sensitivity


# -----------------------------------------------------------------------------
# Layer 7 output: final valuation range
# -----------------------------------------------------------------------------
@dataclass
class FinalRange:
    """Aggregated final valuation range."""
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    model_contributions: dict = field(default_factory=dict)  # Each model's contribution
    weight_explain: str = ""                 # Weighting explanation
    divergence_alert: bool = False           # True when model divergence exceeds 30%


# -----------------------------------------------------------------------------
# Layer 8 output: alert list
# -----------------------------------------------------------------------------
@dataclass
class AlertItem:
    """A single alert item."""
    level: str          # "critical" / "warning"
    message: str
    reason: str
    affected_models: list = field(default_factory=list)
    suggestion: str = ""
