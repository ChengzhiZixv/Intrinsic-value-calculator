# =============================================================================
# Layer 1 - Data Quality Report (quality.py)
# =============================================================================
# Responsibility: generate a DataQualityReport from RawData.
# Checks: missing fields, logical consistency (market cap ≈ price × shares),
# and financial data freshness.
# No imputation is performed; issues are recorded for downstream graceful
# degradation or model disabling.
#
# Adjustable:
# - Financial data staleness threshold (default 6 months) at THRESHOLD_MONTHS below.
# =============================================================================

from datetime import datetime, timedelta
from typing import List

from src.valmod.types import RawData, DataQualityReport

# [Adjustable] Warn if financials have not been updated within this many months
THRESHOLD_MONTHS = 6


def _check_consistency(raw: RawData) -> List[str]:
    """
    Logical consistency check: market cap ≈ price × shares.
    If all three are present and diverge by >5%, add to critical list.
    """
    out = []
    p, m, s = raw.current_price, raw.market_cap, raw.shares
    if p is not None and m is not None and s is not None and s > 0 and p > 0:
        implied_mcap = p * s
        if abs(m - implied_mcap) / max(m, implied_mcap, 1) > 0.05:
            out.append("Market cap inconsistent with price × shares (divergence >5%); verify data source")
    return out


def _check_freshness(raw: RawData) -> List[str]:
    """Data freshness: check days since the latest financial report date. Warn if >THRESHOLD_MONTHS."""
    out = []
    d = raw.latest_financial_date
    if not d:
        return out
    try:
        if isinstance(d, str) and len(d) >= 4:
            year = int(d[:4])
            month = int(d[5:7]) if len(d) >= 7 else 6
            day = int(d[8:10]) if len(d) >= 10 else 1
            latest = datetime(year, month, day)
            delta = datetime.now() - latest
            if delta.days > THRESHOLD_MONTHS * 30:
                out.append(f"Financials not updated in over {THRESHOLD_MONTHS} months; data may be stale")
    except Exception:
        pass
    return out


def build_quality_report(raw: RawData) -> DataQualityReport:
    """
    Generate a data quality report.
    Input:  RawData
    Output: DataQualityReport (missing fields, warnings, critical issues, source log)
    """
    missing = []
    warnings = []
    critical = []

    # ----- Missing field list -----
    if raw.current_price is None:
        missing.append("current_price")
    if raw.market_cap is None:
        missing.append("market_cap")
    if raw.shares is None:
        missing.append("shares")
    if raw.cfo is None:
        missing.append("cfo")
    if raw.revenue is None:
        missing.append("revenue")
    if raw.net_income is None:
        missing.append("net_income")
    if raw.diluted_eps is None:
        missing.append("diluted_eps")
    if raw.ebitda is None:
        missing.append("ebitda")
    if raw.enterprise_value is None:
        missing.append("enterprise_value")
    if raw.capex is None:
        missing.append("capex")

    # ----- Logical consistency -----
    critical.extend(_check_consistency(raw))

    # ----- Data freshness -----
    warnings.extend(_check_freshness(raw))

    # ----- Completeness: fraction of key fields present -----
    key_fields = ["current_price", "market_cap", "shares", "cfo", "revenue", "net_income", "diluted_eps", "ebitda", "enterprise_value"]
    present = sum(1 for f in key_fields if getattr(raw, f, None) is not None)
    completeness = present / len(key_fields) if key_fields else 0.0

    # ----- CFO missing → DCF unavailable -----
    if raw.cfo is None:
        critical.append("CFO missing; DCF model unavailable")

    source_log = f"Data source: Yahoo Finance | Fetched: {raw.fetch_timestamp or 'N/A'}"

    return DataQualityReport(
        completeness=completeness,
        missing=missing,
        warnings=warnings,
        critical=critical,
        source_log=source_log,
    )
