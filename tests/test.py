import sys
import pandas as pd
import yfinance as yf

pd.set_option("display.max_columns", 50)
pd.set_option("display.width", 140)

INFO_KEYS = [
    "shortName", "longName", "symbol", "currency",
    "sector", "industry",
    "exchange", "marketCap", "enterpriseValue",
    "currentPrice", "previousClose",
    "beta",
    "sharesOutstanding",
    "trailingPE", "forwardPE", "priceToBook",
    "trailingEps", "forwardEps",
    "ebitda",
    "totalRevenue", "grossMargins", "operatingMargins", "profitMargins",
]

def safe_get(d, k):
    v = d.get(k, None)
    return v

def show_info(info: dict):
    print("\n=== [info] selected fields ===")
    for k in INFO_KEYS:
        v = safe_get(info, k)
        print(f"{k:>18}: {v}")

    # Shares fallback estimate if possible
    market_cap = safe_get(info, "marketCap")
    price = safe_get(info, "currentPrice")
    shares = safe_get(info, "sharesOutstanding")
    if shares is None and market_cap and price:
        est = market_cap / price
        print(f"{'sharesEst(mcap/px)':>18}: {est}  (estimated)")

def show_history(t: yf.Ticker):
    print("\n=== [price history] last 5 rows (1y, 1d) ===")
    hist = t.history(period="1y", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        print("No price history returned.")
        return
    print(hist.tail(5))

def show_table(df: pd.DataFrame, name: str):
    print(f"\n=== [{name}] ===")
    if df is None or df.empty:
        print("Empty / not available.")
        return

    # yfinance returns columns as periods; show shape + headers
    print(f"shape: {df.shape}")
    print("columns (periods):", list(df.columns)[:6], "..." if df.shape[1] > 6 else "")
    print("rows (line items) sample:", list(df.index)[:12], "..." if len(df.index) > 12 else "")

    # show last 2 columns (most recent periods) if possible
    cols = list(df.columns)
    last_cols = cols[-2:] if len(cols) >= 2 else cols
    print("\nMost recent periods snapshot:")
    print(df[last_cols].head(20))

def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"Probing ticker: {ticker}")

    t = yf.Ticker(ticker)

    # info
    info = {}
    try:
        info = t.info or {}
    except Exception as e:
        print("Failed to read info:", e)

    print("\nInfo keys count:", len(info))
    show_info(info)

    # price history
    try:
        show_history(t)
    except Exception as e:
        print("Failed to read history:", e)

    # financial statements (annual by default)
    try:
        show_table(t.income_stmt, "income_stmt (annual)")
        show_table(t.balance_sheet, "balance_sheet (annual)")
        show_table(t.cashflow, "cashflow (annual)")
    except Exception as e:
        print("Failed to read financial statements:", e)

    # quarterly statements (often useful for recency)
    try:
        show_table(t.quarterly_income_stmt, "quarterly_income_stmt")
        show_table(t.quarterly_balance_sheet, "quarterly_balance_sheet")
        show_table(t.quarterly_cashflow, "quarterly_cashflow")
    except Exception as e:
        print("Failed to read quarterly statements:", e)

if __name__ == "__main__":
    main()