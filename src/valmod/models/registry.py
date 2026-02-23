# =============================================================================
# Layer 5 - Model Registry (registry.py)
# =============================================================================
# Responsibility: invoke each valuation model according to EnabledModels and
# aggregate results into ModelOutputs. Model failures degrade gracefully
# (the failing model outputs None without blocking the pipeline).
#
# Adjustable: no business parameters.
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
    Invoke each model in the enabled list and aggregate outputs.
    Input:  norm, assumptions, raw, enabled, overrides
    Output: ModelOutputs
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

    # ── Step 1: Damodaran PE regression (attempt whenever gEPS is provided) ──
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
            model_warnings.append(f"Damodaran PE computation error: {e}")

    # ── Step 2: Damodaran intrinsic value (run first to obtain WACC for relative valuation) ──
    _computed_wacc = None
    if overrides.get("rf") is not None:
        try:
            res = run_damodaran_iv(raw, overrides)
            damodaran_iv_val = res.get("damodaran_iv")
            damodaran_iv_details = res.get("damodaran_iv_details") or {}
            # Extract discount rate: FCFF → WACC; FCFE/DDM → re
            _computed_wacc = damodaran_iv_details.get("wacc") or damodaran_iv_details.get("re")
        except Exception as e:
            model_warnings.append(f"Damodaran intrinsic value computation error: {e}")
            # Retain error info so the UI shows a specific message rather than a blank or generic prompt
            damodaran_iv_details = {"error": f"Computation error ({type(e).__name__}): {e}"}

    # ── Step 3: Relative valuation (fundamentals-derived multiples using IV's WACC) ──
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
            model_warnings.append(f"Relative valuation computation error: {e}")

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
