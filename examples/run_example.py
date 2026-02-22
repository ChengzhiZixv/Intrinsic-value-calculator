# =============================================================================
# 命令行示例：运行估值
# =============================================================================
# 用法：python examples/run_example.py [TICKER]
# 默认 TICKER=ORCL；可换任意美股代码，如 AAPL、MSFT。
# =============================================================================

import sys
sys.path.insert(0, ".")
from src.valmod.pipeline import run_valuation

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "ORCL"
    out = run_valuation(ticker)
    if "error" in out:
        print("错误:", out["error"])
    else:
        print("Ticker:", out["ticker"])
        print("当前价:", out.get("current_price"))
        print("数据质量:", out["data_quality"]["completeness"], "缺失:", out["data_quality"]["missing"])
        print("假设:", out["assumptions"])
        print("模型输出:", out["model_outputs"])
        print("最终区间:", out["final_range"])
        if out.get("alerts"):
            print("告警:", out["alerts"])
