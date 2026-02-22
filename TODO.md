# 估值系统实现清单

## 📋 当前状态
✅ 项目骨架已建好（28个文件）  
✅ **所有 8 层已完整实现**（能跑通并输出估值）  
✅ 测试用例：ORCL（已通过）  
✅ Streamlit 网页界面已实现  
✅ 命令行示例已实现  

---

## 🎯 阶段1：MVP（已完成 ✅）

### ✅ Layer 1：数据层（Data Layer）
**文件：`src/valmod/data_layer/fetch.py`**

- [x] 用 `yfinance.Ticker(ticker)` 拉取：
  - [x] 市场数据：`info['currentPrice']`, `info['marketCap']`, `info['sharesOutstanding']`
  - [x] 估值字段：`info['trailingPE']`, `info['forwardPE']`, `info['priceToBook']`, `info['enterpriseValue']`, `info['ebitda']`
  - [x] 财报：`financials`, `income_stmt`, `balance_sheet`, `cashflow`（年度优先）
- [x] 填充 `RawData` 对象（见 `types.py`）
- [x] 记录拉取时间戳

**文件：`src/valmod/data_layer/quality.py`**

- [x] 生成 `DataQualityReport`：
  - [x] 缺失字段清单（不插补）
  - [x] 逻辑校验（市值/股价/股本自洽性）
  - [x] 财报时效性（最新财报日期 vs 当前日期，>6个月 → Warning）
- [x] 返回 `SourceLog`（数据来源、拉取时间）

---

### ✅ Layer 2：标准化层（Normalization Layer）
**文件：`src/valmod/normalization/normalize.py`**

- [x] 口径选择：年度优先，若缺则用季度（不强行拼TTM）
- [x] 派生项：
  - [x] `FCF = CFO - CAPEX`（优先用 cashflow 表）
  - [x] `净债务 = Total Debt - Cash`（若可得）
  - [x] 比率：`FCF margin`, `EBITDA margin`, `ROE/ROIC`（能算则算）
- [x] **优雅降级策略**：
  - [x] CAPEX 缺失：用 `PPE 净额年度变化` 近似（标注"CAPEX估算"，触发 Warning）
  - [x] 股本缺失：用 `marketCap / currentPrice` 反推（标注"股本反推估计"）
  - [x] CFO 缺失：不做替代，后续禁用 DCF
- [x] 填充 `NormalizedFinancials` 对象
- [x] 生成 `TransformLog`（记录计算与估算步骤）

---

### ✅ Layer 3：分类与模型选择
**文件：`src/valmod/classification/selector.py`**

- [x] 根据数据可得性决定模型组合：
  - [x] FCF 可得且为正 → 启用 `DCF + 相对估值 + 反向DCF`
  - [x] FCF 不可得但 EPS/PE 可得 → 仅启用 `PE 相对估值`（DCF 置灰）
  - [x] EPS 缺但 revenue 与 marketCap/EV 可得 → 启用 `P/S` 或 `EV/Sales`
  - [x] 关键字段不足 → 返回"数据不足无法估值"+缺失项清单
- [x] 返回 `CompanyTag`, `EnabledModels`, `SelectionRationale`

---

### ✅ Layer 4：假设引擎（Assumption Engine）
**文件：`src/valmod/assumptions/engine.py`**

- [x] **宏观默认**：
  - [x] `折现率 r`：默认 10%（可调，从 `config/analyst_overrides.yaml` 或函数参数）
  - [x] `永续增长 g`：默认 2.5%（可调，提示不宜过高）
- [x] **经营假设**：
  - [x] `显式期年数`：默认 5 年（可调）
  - [x] `显式期增长率`：
    - [x] 优先用历史 revenue/FCF 的 CAGR（窗口：优先3年，不足则2年）
    - [x] CAGR 上限：15%（防止极端值）
    - [x] CAGR 下限：-10%（负增长公司特殊处理）
    - [x] 若算不了，默认 5%（并提示"保守默认值"）
- [x] 支持用户覆盖（`overrides` 参数）
- [x] 生成 `AssumptionChangeLog`（记录默认/用户来源）

---

### ✅ Layer 5：估值模型层（Valuation Models）

#### 5.1 DCF（核心）
**文件：`src/valmod/models/dcf.py`**

- [x] **适用条件检查**：CFO 可得，CAPEX 可得或可估算，股本可得或可反推
- [x] FCFF 模型：
  - [x] 5 年显式期预测（用假设的增长率）
  - [x] WACC 计算（简化版：`r = 折现率`，或后续扩展）
  - [x] 终值计算（Gordon Growth：`TV = FCF5 * (1+g) / (r - g)`）
- [x] 每股估值 = `(显式期现值 + 终值现值) / 股本`
- [x] 计算终值占比（`终值现值 / 总现值`）
- [x] 若终值占比 >70% → 生成 Warning
- [x] 返回：`value_per_share`, `terminal_pct`, `warnings`

#### 5.2 反向 DCF（学习核心输出）
**文件：`src/valmod/models/reverse_dcf.py`**

- [x] **适用条件**：DCF 框架可跑且有当前价格/市值
- [x] 固定三项输出：
  - [x] 为撑起当前价格，未来5年 FCF CAGR 需要达到多少（反推）
  - [x] 对应第5年 FCF 绝对规模
  - [x] 若 revenue 可得：隐含 FCF margin 与历史 FCF margin 对比（合理性提示）
- [x] 返回：`implied_cagr`, `implied_fcf5`, `implied_margin_vs_historical`

#### 5.3 相对估值（能算则算）
**文件：`src/valmod/models/multiples.py`**

- [x] **PE**：需要 `PE` 与 `价格`（或 `EPS`）- **使用稀释 EPS，与 MOOMOO 一致**
- [x] **EV/EBITDA**：需要 `EV` 与 `EBITDA`
- [x] **P/S 或 EV/Sales**：需要 `marketCap/EV` 与 `revenue`
- [x] 输出：相对估值区间（若仅单点则标注"数据限制"）
- [x] 返回：`pe`, `ev_ebitda`, `ev_sales`（能算则算，不能则 None）

#### 5.4 模型注册表
**文件：`src/valmod/models/registry.py`**

- [x] 根据 `EnabledModels` 调用对应模型（dcf / multiples）
- [x] 汇总为 `ModelOutputs` 对象
- [x] 处理模型失败情况（优雅降级）

---

### ✅ Layer 6：情景与敏感性引擎
**文件：`src/valmod/scenario/engine.py`**

- [x] **参数扰动**（固定幅度）：
  - [x] 增长率 ±2%
  - [x] 折现率 ±1%
  - [x] 永续增长 ±0.5%
- [x] 生成三情景：
  - [x] Bear（悲观）：增长率-2%，r+1%，g-0.5%
  - [x] Base（基准）：原始假设
  - [x] Bull（乐观）：增长率+2%，r-1%，g+0.5%
- [x] 单变量敏感性表（可选：增长率 vs 折现率二维矩阵）
- [x] 返回：`low`, `mid`, `high`, `sensitivity`

---

### ✅ Layer 7：模型融合与权重
**文件：`src/valmod/aggregation/weighting.py`**

- [x] **融合规则**：
  - [x] DCF 与相对估值都可用：默认 DCF 60% + 相对 40%（可在页面调）
  - [x] 只有一种可用：直接采用
- [x] 计算模型分歧（`max - min / mid`）
- [x] 若模型分歧 >30% → 触发分歧告警（但不自动调参）
- [x] 返回：`FinalRange`（low/mid/high）+ `ModelContributions` + `WeightExplain`

---

### ✅ Layer 8：智能告警与上下文
**文件：`src/valmod/warnings/context.py`**

- [x] **数据质量告警**：
  - [x] Critical：CFO 缺失、股价/市值/股本无法自洽、关键表缺失导致主要模型不可用
  - [x] Warning：CAPEX 用 PPE 估算、股本用市值反推、字段缺失导致相对估值不完整
- [x] **估值不确定性告警**：
  - [x] DCF 终值占比 >70%：高度依赖长期假设
  - [x] 模型分歧 >30%：需要人工判断假设差异
- [x] **激进会计检测**（通用模块）：
  - [x] 折旧比率预警：`D&A / Revenue` 超过阈值或显著偏离自身历史
  - [x] 折旧与 CAPEX 缺口：若 `D&A >> CAPEX` → 提示"需核对维持性资本开支/资产处置/资本化口径"
  - [x] 现金流质量：`FCF/净利润` 长期偏低 → 提示"盈利与现金流脱节"
- [x] 返回：分级告警列表（问题、原因、影响的模型、建议核对项）

---

### ✅ 主流水线串联
**文件：`src/valmod/pipeline.py`**

- [x] 串联 Layer 1→8：
  1. `fetch_raw(ticker)` → `RawData`
  2. `build_quality_report(raw)` → `DataQualityReport`
  3. `normalize(raw)` → `NormalizedFinancials`
  4. `select_models(norm)` → `EnabledModels`
  5. `build_assumptions(norm, overrides)` → `Assumptions`
  6. `run_all_models(norm, assumptions, raw, enabled)` → `ModelOutputs`
  7. `run_scenarios(assumptions, base_value)` → 三情景
  8. `aggregate(models, dcf_weight, relative_weight)` → `FinalRange`
  9. `build_warnings(quality, models, terminal_pct)` → 告警列表
- [x] **错误处理**：
  - [x] yfinance API 失败重试机制（3次，指数退避）
  - [x] 数据拉取超时处理（30秒超时）
  - [x] 除零错误防护（PE=0、EBITDA=0）
  - [x] 负值处理（负 FCF、负 EBITDA 的说明）
- [x] 返回完整报告字典

---

### ✅ Streamlit 网页界面
**文件：`app.py`**

- [x] 输入 ticker（默认 ORCL）
- [x] 展示数据质量/缺失项
- [x] Sidebar 滑块调整关键假设（r、g、显式期年数、DCF权重）
- [x] 展示模型结果与最终区间
- [x] 展示反向 DCF 隐含条件
- [x] 展示告警列表
- [x] 缓存：`@st.cache_data`（按 ticker + 时间戳缓存）
- [x] 导出：Markdown/JSON（本地保存）

---

## 🎯 阶段2：学习价值增强（部分完成）

- [x] 反向 DCF 输出"隐含 FCF 增速/规模/隐含 margin"
- [x] Layer 8 告警体系完善（终值占比、模型分歧、估算字段告警）
- [x] 引入"激进会计检测"基础版（对能算出的 D&A、CAPEX、Revenue 执行）
- [ ] **压力测试**：用 FTAI 等争议股验证降级与告警是否合理（待验证）

---

## 🎯 阶段3：体验优化（待实现）

- [ ] 缓存强化（Streamlit 缓存已实现，可进一步优化）
- [ ] 导出 Markdown/JSON（JSON 已实现，Markdown 待实现）
- [ ] 图表更清晰（估值区间、敏感性）- 当前为 JSON 展示
- [ ] 可选：历史倍数分位（若数据足够则做，不能就跳过）

---

## 📝 验收标准

### 阶段1 MVP 验收：
- [x] ORCL 能稳定出报告（有估值数字，不是占位 0）
- [x] 缺数据时能正确置灰 DCF 并解释原因
- [x] 数据质量报告能正确显示缺失项
- [x] 三情景区间能正确计算
- [x] 告警能正确触发（终值占比>70%、模型分歧>30%等）

---

## 🔍 关键注意事项

1. **所有参数可覆盖**：在 `config/analyst_overrides.yaml` 或函数参数中支持用户调整
2. **所有修改记录日志**：假设修改、数据估算都要记录来源
3. **优雅降级**：数据缺失时不乱算，明确标注并禁用相关模型
4. **分析师必须研究的参数**：用 `# [ANALYST_REQUIRED]` 标注（如 ERP、Beta 截断、一次性项目定义、长期增长 g、估值规则分桶、终值口径、WACC 细节）
5. **PE 使用稀释 EPS**：与 MOOMOO 等平台一致（yfinance 的 trailingPE 为未稀释，不可靠）
