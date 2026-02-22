"""建好后在项目根目录运行: python examples/run_orcl.py"""
import sys
sys.path.insert(0, ".")
from src.valmod.pipeline import run_valuation

if __name__ == "__main__":
    out = run_valuation("ORCL")
    print("Ticker:", out["ticker"])
    print("Data quality:", out["data_quality"])
    print("Assumptions:", out["assumptions"])
    print("Final range:", out["final_range"])
