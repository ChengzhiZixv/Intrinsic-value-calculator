# =============================================================================
# Layer 1 - Data Fetching (fetch.py)
# =============================================================================
# Responsibility: fetch raw data from Yahoo Finance for any US stock ticker
# and populate a RawData object. No valuation or imputation is performed here;
# missing fields remain None.
#
# Adjustable: no business parameters. If yfinance field names change, update
# the key mappings in this file.
# =============================================================================

import os
import shutil
import tempfile
import time
from datetime import datetime
from typing import Optional

# Fix: certifi certificate path containing non-ASCII characters cannot be read
# by libcurl. Copy cert to a temp directory and monkey-patch certifi.where().
def _fix_ssl_cert():
    try:
        import certifi
        cert_path = certifi.where()
        if any(ord(c) > 127 for c in cert_path):
            tmp = os.path.join(tempfile.gettempdir(), "cacert_valmod.pem")
            if not os.path.exists(tmp):
                shutil.copy2(cert_path, tmp)
            os.environ["CURL_CA_BUNDLE"] = tmp
            os.environ["REQUESTS_CA_BUNDLE"] = tmp
            certifi.where = lambda: tmp  # curl_cffi calls certifi.where() directly

    except Exception:
        pass

_fix_ssl_cert()

import yfinance as yf

from src.valmod.types import RawData


def _safe_float(val, default: Optional[float] = None) -> Optional[float]:
    """
    Safely convert to float. Returns default if value is None, NaN, infinity,
    or otherwise non-numeric. Prevents downstream division-by-zero or logic errors
    caused by yfinance returning abnormal values.
    """
    if val is None:
        return default
    try:
        f = float(val)
        if f != f or abs(f) == float("inf"):  # NaN or inf
            return default
        return f
    except (TypeError, ValueError):
        return default


def fetch_raw(ticker: str) -> RawData:
    """
    Fetch raw data for the given ticker from Yahoo Finance.
    Input:  ticker, e.g. "AAPL", "ORCL", "MSFT"
    Output: RawData object (missing fields are None)
    """
    t = yf.Ticker(ticker)
    info = t.info
    fetch_ts = datetime.now().isoformat()

    # ----- Market data -----
    current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    market_cap = _safe_float(info.get("marketCap"))
    shares = _safe_float(info.get("sharesOutstanding"))  # typically diluted shares outstanding
    enterprise_value = _safe_float(info.get("enterpriseValue"))

    # ----- Valuation fields (yfinance PE is undiluted — for reference only;
    #        the system computes diluted PE independently) -----
    trailing_pe = _safe_float(info.get("trailingPE"))
    forward_pe = _safe_float(info.get("forwardPE"))
    price_to_book = _safe_float(info.get("priceToBook"))
    ebitda = _safe_float(info.get("ebitda"))

    # ----- Financial statements: annual preferred
    #        (yfinance row/column structure may vary across versions) -----
    def _first_val(df, *keys):
        if df is None or df.empty:
            return None
        for k in keys:
            try:
                if k in df.index:
                    s = df.loc[k]
                elif k in df.columns:
                    s = df[k]
                else:
                    continue
                v = s.iloc[0] if hasattr(s, "iloc") and len(s) else (s[0] if hasattr(s, "__getitem__") and len(s) else None)
                return _safe_float(v)
            except Exception:
                pass
        return None

    income = t.income_stmt
    balance = t.balance_sheet
    cashflow = t.cashflow

    revenue = _first_val(income, "Total Revenue", "Operating Revenue", "Revenue")
    net_income = _first_val(income, "Net Income", "Net Income Common Stockholders")
    diluted_eps = _first_val(income, "Diluted EPS")
    latest_date = str(income.columns[0]) if income is not None and not income.empty and len(income.columns) else None

    cfo = _first_val(cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex_raw = _first_val(cashflow, "Capital Expenditure")
    capex = -abs(capex_raw) if capex_raw is not None and capex_raw > 0 else capex_raw if capex_raw is not None else None
    depreciation_amortization = _first_val(cashflow, "Depreciation And Amortization", "Depreciation")
    if latest_date is None and cashflow is not None and not cashflow.empty and len(cashflow.columns):
        latest_date = str(cashflow.columns[0])

    total_debt = _first_val(balance, "Total Debt", "Long Term Debt")
    cash = _first_val(balance, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")

    ppe_net = _first_val(balance, "Property Plant And Equipment Net", "Net PPE") if balance is not None else None
    ppe_net_prior = None
    if balance is not None and not balance.empty and balance.shape[1] >= 2:
        for k in ["Property Plant And Equipment Net", "Net PPE"]:
            if k in balance.index:
                try:
                    ppe_net_prior = _safe_float(balance.loc[k].iloc[1])
                except Exception:
                    pass
                break

    beta = _safe_float(info.get("beta"))
    payout_ratio = _safe_float(info.get("payoutRatio"))
    sector = info.get("sector") or None
    industry = info.get("industry") or None

    # ----- Fields required by Damodaran intrinsic value models -----
    operating_income = _first_val(income, "Operating Income", "EBIT", "Total Operating Income")

    # Working capital = current assets - current liabilities (current and prior year)
    ca = _first_val(balance, "Total Current Assets", "Current Assets")
    cl = _first_val(balance, "Total Current Liabilities", "Current Liabilities")
    working_capital = (ca - cl) if ca is not None and cl is not None else None

    ca_prior, cl_prior = None, None
    if balance is not None and not balance.empty and balance.shape[1] >= 2:
        for k in ["Total Current Assets", "Current Assets"]:
            if k in balance.index:
                try:
                    ca_prior = _safe_float(balance.loc[k].iloc[1])
                except Exception:
                    pass
                break
        for k in ["Total Current Liabilities", "Current Liabilities"]:
            if k in balance.index:
                try:
                    cl_prior = _safe_float(balance.loc[k].iloc[1])
                except Exception:
                    pass
                break
    working_capital_prior = (ca_prior - cl_prior) if ca_prior is not None and cl_prior is not None else None

    # Net debt issuance (positive = net new borrowing, negative = net repayment)
    net_debt_issuance = _first_val(cashflow, "Net Issuance Payments Of Debt", "Net Long Term Debt Issuance")
    if net_debt_issuance is None:
        ltd_i = _first_val(cashflow, "Long Term Debt Issuance") or 0.0
        ltd_r = _first_val(cashflow, "Long Term Debt Payments") or 0.0
        std_i = _first_val(cashflow, "Short Term Debt Issuance") or 0.0
        std_r = _first_val(cashflow, "Short Term Debt Payments") or 0.0
        total_net = (ltd_i or 0) + (ltd_r or 0) + (std_i or 0) + (std_r or 0)
        net_debt_issuance = total_net if total_net != 0 else None

    # Total dividends paid (absolute value)
    div_raw = _first_val(cashflow, "Common Stock Dividend Paid", "Cash Dividends Paid",
                         "Payment Of Dividends", "Dividends Paid")
    dividends_paid = abs(div_raw) if div_raw is not None else None

    # ── Fallback calculations (derived from other available data when yfinance fields are missing) ──
    # Payout ratio = dividends paid / net income (capped at 100%)
    if payout_ratio is None and dividends_paid is not None and net_income is not None and net_income > 0:
        payout_ratio = min(dividends_paid / net_income, 1.0)

    # Diluted EPS = net income / diluted shares (back-calculated when income statement field is missing)
    if diluted_eps is None and net_income is not None and shares is not None and shares > 0:
        diluted_eps = net_income / shares

    return RawData(
        ticker=ticker,
        current_price=current_price,
        market_cap=market_cap,
        shares=shares,
        enterprise_value=enterprise_value,
        trailing_pe=trailing_pe,
        forward_pe=forward_pe,
        price_to_book=price_to_book,
        ebitda=ebitda,
        revenue=revenue,
        net_income=net_income,
        cfo=cfo,
        capex=capex,
        total_debt=total_debt,
        cash=cash,
        diluted_eps=diluted_eps,
        depreciation_amortization=depreciation_amortization,
        ppe_net=ppe_net,
        ppe_net_prior=ppe_net_prior,
        latest_financial_date=latest_date,
        fetch_timestamp=fetch_ts,
        beta=beta,
        payout_ratio=payout_ratio,
        sector=sector,
        industry=industry,
        operating_income=operating_income,
        working_capital=working_capital,
        working_capital_prior=working_capital_prior,
        net_debt_issuance=net_debt_issuance,
        dividends_paid=dividends_paid,
    )
