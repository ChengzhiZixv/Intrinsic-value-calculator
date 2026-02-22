# Streamlit 入口。运行: streamlit run app.py
import streamlit as st
st.set_page_config(page_title="美股估值", layout="wide")
ticker = st.text_input("Ticker", value="AAPL", max_chars=10)
if ticker:
    st.info("接入 pipeline 后在此调用 run_valuation(ticker) 并展示结果。")
