# =============================================================================
# Layer 5 - 模型注册表（registry.py）
# =============================================================================
# 职责：根据 EnabledModels 调用各估值模型，汇总为 ModelOutputs。
# 处理模型失败时优雅降级（该模型输出 None，不阻断流水线）。
#
# 你可调整：无业务参数。
# =============================================================================

from typing import Optional

from src.valmod.types import NormalizedFinancials, Assumptions, RawData, ModelOutputs
from src.valmod.models.multiples import run_multiples, run_damodaran_pe
from src.valmod.models.damodaran_iv import run_damodaran_iv


def run_all_models(
    norm: NormalizedFinancials,
    assumptions: Assumptions,
    raw: RawData,
    enabled: list,
    overrides: Optional[dict] = None,
) -> ModelOutputs:
    """
    按 enabled 列表调用各模型，汇总输出。
    输入：norm, assumptions, raw, enabled, overrides
    输出：ModelOutputs
    """
    overrides = overrides or {}
    model_warnings = []

    ev_ebitda_val = None
    ev_sales_val = None
    multiples_details = None
    damodaran_pe_val = None
    damodaran_pe_details = None
    damodaran_iv_val = None
    damodaran_iv_details = None

    # ── Step 1：Damodaran PE 回归（只要有 gEPS 就尝试） ──────────────────────
    gEPS = overrides.get("gEPS")
    if gEPS is not None:
        try:
            res = run_damodaran_pe(
                raw,
                gEPS=gEPS,
                sector_beta_unlevered=overrides.get("sector_beta_unlevered"),
                tax_rate=overrides.get("tax_rate", 0.25),
            )
            damodaran_pe_val = res.get("damodaran_pe")
            damodaran_pe_details = res.get("damodaran_pe_details")
        except Exception as e:
            model_warnings.append(f"Damodaran PE 计算异常: {e}")

    # ── Step 2：Damodaran 内在价值（优先运行，以获取 WACC 供相对估值使用）──
    _computed_wacc = None
    if overrides.get("rf") is not None:
        try:
            res = run_damodaran_iv(raw, overrides)
            damodaran_iv_val = res.get("damodaran_iv")
            damodaran_iv_details = res.get("damodaran_iv_details") or {}
            # 提取折现率：FCFF → WACC，FCFE/DDM → re
            _computed_wacc = damodaran_iv_details.get("wacc") or damodaran_iv_details.get("re")
        except Exception as e:
            model_warnings.append(f"达莫达兰内在价值计算异常: {e}")

    # ── Step 3：相对估值（基本面推导倍数，使用 IV 计算的 WACC） ─────────────
    if "ev_ebitda" in enabled or "ev_sales" in enabled:
        try:
            mult_overrides = dict(overrides)
            if _computed_wacc is not None:
                mult_overrides["_computed_wacc"] = _computed_wacc
            mult = run_multiples(norm, raw, mult_overrides)
            ev_ebitda_val = mult.get("ev_ebitda")
            ev_sales_val = mult.get("ev_sales")
            multiples_details = mult.get("details")
        except Exception as e:
            model_warnings.append(f"相对估值计算异常: {e}")

    return ModelOutputs(
        ev_ebitda=ev_ebitda_val,
        ev_sales=ev_sales_val,
        multiples_details=multiples_details,
        damodaran_pe=damodaran_pe_val,
        damodaran_pe_details=damodaran_pe_details,
        damodaran_iv=damodaran_iv_val,
        damodaran_iv_details=damodaran_iv_details,
        model_warnings=model_warnings,
    )
