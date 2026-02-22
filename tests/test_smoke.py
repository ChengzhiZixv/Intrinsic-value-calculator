"""最小测试：能跑通 run_valuation 不报错。"""
import sys
sys.path.insert(0, ".")
from src.valmod.pipeline import run_valuation

def test_run_valuation():
    out = run_valuation("ORCL")
    assert out["ticker"] == "ORCL"
    assert "final_range" in out
