# =============================================================================
# 主流水线（pipeline.py）
# =============================================================================
# 职责：串联 Layer 1～8，输入 Ticker 输出完整估值报告。
# 支持：config/analyst_overrides.yaml 加载；overrides 参数覆盖；重试与错误处理。
#
# 你可调整：
# - 通过 config/analyst_overrides.yaml 或 run_valuation(ticker, overrides={...})
# - 所有 [ANALYST_REQUIRED] 参数均可覆盖
# =============================================================================

import os
import time
from dataclasses import replace as _dc_replace
from pathlib import Path
from typing import Any, Optional

import yaml

from src.valmod.types import (
    RawData,
    DataQualityReport,
    NormalizedFinancials,
    Assumptions,
    ModelOutputs,
    FinalRange,
    SelectionResult,
    AlertItem,
)
from src.valmod.data_layer.fetch import fetch_raw
from src.valmod.data_layer.quality import build_quality_report
from src.valmod.normalization.normalize import normalize
from src.valmod.classification.selector import select_models
from src.valmod.assumptions.engine import build_assumptions
from src.valmod.models.registry import run_all_models
from src.valmod.aggregation.weighting import aggregate
from src.valmod.warnings.context import build_warnings

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2.0

_B = 1_000_000_000.0


def _apply_raw_overrides(raw: "RawData", params: dict) -> "RawData":
    """
    将用户在卡片内补填的财报数据应用到 RawData 对象。
    约定：
      raw_diluted_eps        - 稀释EPS，直接美元值（如 6.08）
      raw_payout_ratio       - 派息率，小数（如 0.035）
      raw_operating_income_b - EBIT，单位 $B
      raw_capex_b            - 资本开支，单位 $B（正数，模型内部取 abs）
      raw_da_b               - 折旧摊销，单位 $B
      raw_net_income_b       - 净利润，单位 $B
      raw_total_debt_b       - 总债务，单位 $B
      raw_cash_b             - 现金，单位 $B
      raw_shares_b           - 稀释股本，单位 亿股（×1e8）→ 实际传入以股为单位 $B（×1e9）
      raw_ebitda_b           - EBITDA，单位 $B
      raw_revenue_b          - 营收，单位 $B
      raw_dividends_paid_b   - 已付股息总额，单位 $B
      raw_net_debt_issuance_b- 净债务融资额，单位 $B
    """
    kwargs = {}
    if params.get("raw_diluted_eps") is not None:
        kwargs["diluted_eps"] = float(params["raw_diluted_eps"])
    if params.get("raw_payout_ratio") is not None:
        kwargs["payout_ratio"] = float(params["raw_payout_ratio"])

    _b_map = {
        "raw_operating_income_b": "operating_income",
        "raw_capex_b":            "capex",
        "raw_da_b":               "depreciation_amortization",
        "raw_net_income_b":       "net_income",
        "raw_total_debt_b":       "total_debt",
        "raw_cash_b":             "cash",
        "raw_shares_b":           "shares",
        "raw_ebitda_b":           "ebitda",
        "raw_revenue_b":          "revenue",
        "raw_dividends_paid_b":   "dividends_paid",
        "raw_net_debt_issuance_b":"net_debt_issuance",
    }
    for param_key, field in _b_map.items():
        v = params.get(param_key)
        if v is not None:
            kwargs[field] = float(v) * _B

    return _dc_replace(raw, **kwargs) if kwargs else raw


def _load_config() -> dict:
    """加载 config/analyst_overrides.yaml（若存在）。"""
    for p in [Path("config/analyst_overrides.yaml"), Path(__file__).parent.parent.parent / "config" / "analyst_overrides.yaml"]:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}


def run_valuation(ticker: str, overrides: Optional[dict] = None) -> dict[str, Any]:
    """
    估值主入口。输入任意美股 Ticker，输出完整报告。
    若调用方传入 overrides（如 UI 滑块），则仅用 overrides，不用 config 文件。
    """
    overrides = overrides or {}
    if overrides:
        params = dict(overrides)
    else:
        params = _load_config()

    raw = None
    for attempt in range(MAX_RETRIES):
        try:
            raw = fetch_raw(ticker)
            raw = _apply_raw_overrides(raw, params)  # 应用用户补填的财报数据
            break
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                return {
                    "ticker": ticker,
                    "error": f"数据拉取失败（已重试 {MAX_RETRIES} 次）: {e}",
                    "data_quality": {"completeness": 0, "missing": ["fetch_failed"], "warnings": [], "critical": [str(e)]},
                }
            time.sleep(RETRY_DELAY * (2**attempt))

    quality = build_quality_report(raw)
    norm = normalize(raw)
    selection = select_models(norm, sector=raw.sector)
    assumptions = build_assumptions(norm, params)
    models = run_all_models(norm, assumptions, raw, selection.enabled_models, params)
    final = aggregate(models)
    iv_terminal_pct = (models.damodaran_iv_details or {}).get("terminal_pct")
    alerts = build_warnings(quality, models, iv_terminal_pct, raw, norm)

    def _serialize(obj):
        if hasattr(obj, "__dict__") and not isinstance(obj, (str, int, float, bool, type(None))):
            if hasattr(obj, "level"):
                return {"level": obj.level, "message": obj.message, "reason": obj.reason, "suggestion": obj.suggestion}
            return {k: _serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
        if isinstance(obj, list):
            return [_serialize(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        return obj

    def _b(v):
        return round(v / _B, 4) if v is not None else None

    return {
        "ticker": ticker,
        "current_price": raw.current_price,
        "sector": raw.sector,
        "industry": raw.industry,
        "financials": {
            # 直接值（非$B）
            "diluted_eps":   raw.diluted_eps,
            "payout_ratio":  raw.payout_ratio,
            "beta":          raw.beta,
            # $B 单位（便于 UI 展示与比较）
            "operating_income_b":    _b(raw.operating_income),
            "capex_b":               _b(abs(raw.capex)) if raw.capex is not None else None,
            "da_b":                  _b(abs(raw.depreciation_amortization)) if raw.depreciation_amortization is not None else None,
            "net_income_b":          _b(raw.net_income),
            "total_debt_b":          _b(raw.total_debt),
            "cash_b":                _b(raw.cash),
            "shares_b":              _b(raw.shares),
            "ebitda_b":              _b(raw.ebitda),
            "revenue_b":             _b(raw.revenue),
            "market_cap_b":          _b(raw.market_cap),
            "dividends_paid_b":      _b(raw.dividends_paid),
            "net_debt_issuance_b":   _b(raw.net_debt_issuance),
            "working_capital_b":     _b(raw.working_capital),
        },
        "recommended_model": selection.recommended_model,
        "recommended_reason": selection.recommended_reason,
        "data_quality": {
            "completeness": quality.completeness,
            "missing": quality.missing,
            "warnings": quality.warnings,
            "critical": quality.critical,
            "source_log": quality.source_log,
        },
        "normalized": {
            "fcf": norm.fcf,
            "revenue": norm.revenue,
            "ebitda": norm.ebitda,
            "net_debt": norm.net_debt,
            "shares_diluted": norm.shares_diluted,
            "transform_log": norm.transform_log,
        },
        "selection": {"enabled_models": selection.enabled_models, "rationale": selection.rationale},
        "assumptions": {
            "discount_rate": assumptions.discount_rate,
            "perpetual_growth": assumptions.perpetual_growth,
            "explicit_years": assumptions.explicit_years,
            "explicit_growth_rate": assumptions.explicit_growth_rate,
            "assumption_log": assumptions.assumption_log,
        },
        "model_outputs": {
            "ev_ebitda": models.ev_ebitda,
            "ev_sales": models.ev_sales,
            "multiples_details": models.multiples_details,
            "damodaran_pe": models.damodaran_pe,
            "damodaran_pe_details": models.damodaran_pe_details,
            "damodaran_iv": models.damodaran_iv,
            "damodaran_iv_details": models.damodaran_iv_details,
        },
        "final_range": {"low": final.low, "mid": final.mid, "high": final.high, "weight_explain": final.weight_explain, "divergence_alert": final.divergence_alert, "model_contributions": getattr(final, "model_contributions", {})},
        "alerts": _serialize(alerts),
    }
