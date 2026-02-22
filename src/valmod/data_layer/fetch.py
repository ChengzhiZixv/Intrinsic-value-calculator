# =============================================================================
# Layer 1 - 数据拉取（fetch.py）
# =============================================================================
# 职责：输入任意美股 Ticker，从 Yahoo Finance 拉取原始数据，填充 RawData。
# 不做任何估值、不做插补；缺失字段保持 None。
#
# 你可调整：
# - 无业务参数，仅数据拉取。若 yfinance 字段名变化，可在此处修改映射。
# =============================================================================

import os
import shutil
import tempfile
import time
from datetime import datetime
from typing import Optional

# 修复：certifi 证书路径含中文时 libcurl 无法读取，复制到临时目录并 monkey-patch
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
            certifi.where = lambda: tmp  # curl_cffi 直接调用 certifi.where()，需 patch

    except Exception:
        pass

_fix_ssl_cert()

import yfinance as yf

from src.valmod.types import RawData


def _safe_float(val, default: Optional[float] = None) -> Optional[float]:
    """
    安全转换为 float。若为 None、NaN、无穷大或非数字，返回 default。
    用于避免 yfinance 返回异常值导致后续除零或逻辑错误。
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
    从 Yahoo Finance 拉取指定 Ticker 的原始数据。
    输入：ticker，如 "AAPL", "ORCL", "MSFT"
    输出：RawData 对象（缺失字段为 None）
    """
    t = yf.Ticker(ticker)
    info = t.info
    fetch_ts = datetime.now().isoformat()

    # ----- 市场数据 -----
    current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    market_cap = _safe_float(info.get("marketCap"))
    shares = _safe_float(info.get("sharesOutstanding"))  # 通常为稀释股本
    enterprise_value = _safe_float(info.get("enterpriseValue"))

    # ----- 估值字段（yfinance 的 PE 为未稀释，仅作参考；本系统会自行计算稀释 PE）-----
    trailing_pe = _safe_float(info.get("trailingPE"))
    forward_pe = _safe_float(info.get("forwardPE"))
    price_to_book = _safe_float(info.get("priceToBook"))
    ebitda = _safe_float(info.get("ebitda"))

    # ----- 财报：年度优先（yfinance 行/列结构可能因版本不同）-----
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

    # ----- 达莫达兰内在价值模型所需字段 -----
    operating_income = _first_val(income, "Operating Income", "EBIT", "Total Operating Income")

    # 营运资本 = 流动资产 - 流动负债（当年与上年）
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

    # 净债务融资额（正=净借入，负=净偿还）
    net_debt_issuance = _first_val(cashflow, "Net Issuance Payments Of Debt", "Net Long Term Debt Issuance")
    if net_debt_issuance is None:
        ltd_i = _first_val(cashflow, "Long Term Debt Issuance") or 0.0
        ltd_r = _first_val(cashflow, "Long Term Debt Payments") or 0.0
        std_i = _first_val(cashflow, "Short Term Debt Issuance") or 0.0
        std_r = _first_val(cashflow, "Short Term Debt Payments") or 0.0
        total_net = (ltd_i or 0) + (ltd_r or 0) + (std_i or 0) + (std_r or 0)
        net_debt_issuance = total_net if total_net != 0 else None

    # 已支付股息总额（绝对值）
    div_raw = _first_val(cashflow, "Common Stock Dividend Paid", "Cash Dividends Paid",
                         "Payment Of Dividends", "Dividends Paid")
    dividends_paid = abs(div_raw) if div_raw is not None else None

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
