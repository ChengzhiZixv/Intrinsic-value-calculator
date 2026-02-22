# How we value Oracle (plain-language)

This is how the project values a ticker like Oracle (ORCL) end-to-end. No code.

---

## 1. Data

- We pull from Yahoo Finance: price, market cap, shares, income statement, balance sheet, cash flow (annual).
- We read: revenue, net income, CFO (operating cash flow), CapEx, debt, cash, diluted EPS, EBITDA.
- We do **not** fill in missing numbers; we flag what’s missing.

## 2. Normalization

- **FCF** = CFO − CapEx. If CapEx is missing we can approximate it from change in PPE (and flag it).
- **Net debt** = Total debt − Cash.
- **Shares**: we use diluted shares (from Yahoo or, if missing, market cap / price).
- We compute ratios we need (e.g. FCF margin) only when we have the inputs.

## 3. Which models run

- If we have **positive FCF and shares** → we run **DCF** and **reverse DCF**.
- If we have **earnings and shares** → we run **PE-based** valuation (PE anchor × diluted EPS).
- If we have **EBITDA** → we run **EV/EBITDA** (anchor × EBITDA → EV, then EV − net debt → equity value, ÷ shares).
- If we have **revenue** → we run **EV/Sales** (anchor × revenue → EV, then same to per share).

For Oracle we typically have FCF and earnings, so we run DCF, reverse DCF, PE, and often EV/EBITDA and EV/Sales.

## 4. DCF (forward)

- We take **current FCF** and grow it for **5 years** at the **explicit-period growth** you set (e.g. 5%).
- After year 5 we assume FCF grows forever at **perpetual growth** (e.g. 2.5%).
- We **discount** all those future cash flows at the **discount rate** you set (e.g. 10%).
- That gives **enterprise value**; we divide by **diluted shares** to get **DCF value per share**.

So for Oracle: one number (DCF per share) comes from: today’s FCF, 5y growth, long-term growth, and discount rate.

## 5. Relative (PE / EV multiples)

- **PE**: we use your **PE anchor** (e.g. 20) × **diluted EPS** → fair value per share.
- **EV/EBITDA**: **EV** = anchor × EBITDA; **equity** = EV − net debt; **per share** = equity ÷ shares.
- **EV/Sales**: same idea with revenue.

These give alternative “fair” prices per share. They depend heavily on the **anchors** you choose (PE, EV/EBITDA, EV/Sales).

## 6. Blending

- We take **DCF value** and the **relative** values we have.
- We blend them with the **DCF weight** and **relative weight** you set (e.g. 60% DCF, 40% relative).
- If only one model is available, we use that one.
- That produces the **mid** estimate; we also show **low/high** (from scenario or min/max of models).

So for Oracle the “result” you see is this blended value, driven by your assumptions and anchors.

## 7. Reverse DCF

- We ask: if the **current stock price** were “fair”, what **5-year FCF growth rate** would justify it?
- We solve for that **implied growth rate** (and implied Year-5 FCF).
- So you see: “At current price, the market is implying ~X% FCF growth per year.”

For growth names (e.g. PLTR) this is often more useful than a single blended number: it tells you what growth is baked into the price.

---

## Summary for Oracle

- We value Oracle by: **(1)** DCF (5y explicit FCF + terminal value, with your r and g), **(2)** PE and EV multiples with your anchors, **(3)** blending with your DCF/relative weights.
- All “key assumptions” (discount rate, perpetual growth, explicit growth, PE anchor, weights) are what **you** set; changing them **should** change the valuation (and in the app they now drive it directly).
- Reverse DCF is shown so you can see what growth the current price implies, instead of only a point estimate.
