# =============================================================================
# Layer 1 - 数据质量报告（quality.py）
# =============================================================================
# 职责：根据 RawData 生成 DataQualityReport。
# 检查：缺失字段、逻辑自洽性（市值≈股价×股本）、财报时效性。
# 不做插补；仅记录问题供后续层「优雅降级」或禁用模型。
#
# 你可调整：
# - 财报过期阈值（默认 6 个月）在下方 THRESHOLD_MONTHS 处。
# =============================================================================

from datetime import datetime, timedelta
from typing import List

from src.valmod.types import RawData, DataQualityReport

# [可调] 财报超过此月数未更新则触发 Warning
THRESHOLD_MONTHS = 6


def _check_consistency(raw: RawData) -> List[str]:
    """
    逻辑自洽性检查：市值 ≈ 股价 × 股本。
    若三者都有且偏差 >5%，加入 critical。
    """
    out = []
    p, m, s = raw.current_price, raw.market_cap, raw.shares
    if p is not None and m is not None and s is not None and s > 0 and p > 0:
        implied_mcap = p * s
        if abs(m - implied_mcap) / max(m, implied_mcap, 1) > 0.05:
            out.append("市值与股价×股本不一致（偏差>5%），请核对数据源")
    return out


def _check_freshness(raw: RawData) -> List[str]:
    """财报时效性：最新财报日期距今天数。超过 THRESHOLD_MONTHS 则 Warning。"""
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
                out.append(f"财报已超过 {THRESHOLD_MONTHS} 个月未更新，数据可能滞后")
    except Exception:
        pass
    return out


def build_quality_report(raw: RawData) -> DataQualityReport:
    """
    生成数据质量报告。
    输入：RawData
    输出：DataQualityReport（缺失项、警告、严重问题、来源日志）
    """
    missing = []
    warnings = []
    critical = []

    # ----- 缺失字段清单 -----
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

    # ----- 逻辑自洽性 -----
    critical.extend(_check_consistency(raw))

    # ----- 时效性 -----
    warnings.extend(_check_freshness(raw))

    # ----- 完整度：关键字段占比 -----
    key_fields = ["current_price", "market_cap", "shares", "cfo", "revenue", "net_income", "diluted_eps", "ebitda", "enterprise_value"]
    present = sum(1 for f in key_fields if getattr(raw, f, None) is not None)
    completeness = present / len(key_fields) if key_fields else 0.0

    # ----- CFO 缺失导致 DCF 不可用 -----
    if raw.cfo is None:
        critical.append("CFO 缺失，DCF 模型不可用")

    source_log = f"数据来源: Yahoo Finance | 拉取时间: {raw.fetch_timestamp or 'N/A'}"

    return DataQualityReport(
        completeness=completeness,
        missing=missing,
        warnings=warnings,
        critical=critical,
        source_log=source_log,
    )
