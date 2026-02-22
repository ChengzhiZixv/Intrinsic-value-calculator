# 美股估值系统（个人学习版）

**输入任意美股 Ticker，输出估值区间 + 关键假设 + 敏感性 + 告警。**  
适用于所有美股（如 AAPL、MSFT、GOOGL、ORCL 等），不是只给某一只股票用。数据来源：Yahoo Finance，本地网页：Streamlit。

> ⚠️ **注意**：YFinance 给出的 PE 是**未稀释**的 PE，用其作为评判标准不可靠。本系统会自行计算**稀释后 PE**，使结果与 MOOMOO 等平台更接近。

## 建好文件后你能做什么

1. **跑网页**：`pip install -r requirements.txt` 然后 `streamlit run app.py`，在页面输入**任意美股代码**看估值。
2. **命令行跑一次估值**：`python examples/run_example.py` 默认跑 ORCL；`python examples/run_example.py AAPL` 跑苹果；换任意 Ticker 即可。
3. **按层填逻辑**：从 `src/valmod/data_layer/fetch.py` 开始，按规划书逐层实现；每层输入输出在 `types.py` 里定义。

3. **调参**：阅读 `调参指南.md`，通过人类语言理解各参数含义，在 `config/analyst_overrides.yaml` 或 Streamlit 侧边栏调整，无需改代码逻辑。

估值结果仅供学习，不构成投资建议。
