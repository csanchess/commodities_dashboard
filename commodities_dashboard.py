# commodities_fx_compliance_dashboard_v4.py
import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
import io
import requests
import numpy as np

st.set_page_config(page_title="Commodities, FX & Compliance Carbon Dashboard (v4)", layout="wide")
st.title("🌍 Commodities, FX & Compliance Carbon Dashboard — v4")
st.markdown("""
Daily dashboard combining commodities, major FX pairs and **compliance carbon market prices**.
- Data: Yahoo Finance where possible; placeholders/APIs for compliance markets that are not on Yahoo.
- PDF export: Generate a multi-page PDF snapshot of tables + charts.
""")

# ---------------------
# SYMBOLS / CONFIG
# ---------------------
# Commodities & others (yfinance tickers where available)
commodities = {
    # Energy
    "Crude Oil (WTI)": "CL=F",
    "Brent Oil": "BZ=F",
    "Natural Gas (Henry Hub, US)": "NG=F",
    "EU Gas (TTF)": "TTF=F",   # may be available via Yahoo depending on region
    "LNG (JKM, Asia proxy)": "JKM=F",

    # Metals
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Copper": "HG=F",
    "Aluminum": "ALI=F",

    # Agriculture / softs
    "Corn": "ZC=F",
    "Wheat": "ZW=F",
    "Soybeans": "ZS=F",
    "Coffee": "KC=F",
    "Cocoa": "CC=F",
    "Live Cattle (Beef)": "LE=F",

    # Plastics proxy
    "Ethylene (proxy)": "ETHUSD=X",
}

# FX pairs (Yahoo Finance tickers)
# Note: All tickers are USD-based pairs where possible. If the inverse pair is used, conversion is handled automatically later.
currencies = {
    "GBP/USD": "GBPUSD=X",     # USD per GBP
    "EUR/USD": "EURUSD=X",     # USD per EUR
    "USD/BRL": "USDBRL=X",     # BRL per USD
    "USD/CNY": "USDCNY=X",     # CNY per USD (RMB)
    "USD/JPY": "USDJPY=X",     # JPY per USD
    "USD/NOK": "USDNOK=X",     # NOK per USD
    "USD/CAD": "USDCAD=X",     # CAD per USD
    "USD/AUD": "AUDUSD=X",     # Yahoo only provides AUDUSD, so invert
    "CHF/USD": "CHFUSD=X",     # USD per CHF
}

# Compliance carbon markets (mix of yfinance tickers and placeholders)
# NOTE: many compliance markets do not have reliable Yahoo tickers. Where a ticker exists we use it;
# otherwise the app will show "No ticker - requires API/scrape" and NaN price until you wire a source.
compliance_markets = {
    "EU ETS (EUA)": {"ticker": "C02.F", "unit": "€/t"},
    "UK ETS": {"ticker": None, "unit": "£/t"},
    "California (CARB)": {"ticker": None, "unit": "US$/t"},
    "RGGI": {"ticker": None, "unit": "US$/t"},
    "New Zealand (NZ ETS)": {"ticker": None, "unit": "NZ$/t"},
    "South Korea (K-ETS)": {"ticker": None, "unit": "KRW/t"},
    "China National ETS": {"ticker": None, "unit": "RMB/t"},
    "Core Carbon Principles (CCP)": {"ticker": None, "unit": "US$/t"},
    "CORSIA (Phase 1)": {"ticker": None, "unit": "US$/t"},
    "CBL Global (GEO)": {"ticker": "GEO=F", "unit": "US$/t"},
    "CBL Nature-Based (NGO)": {"ticker": "NGO=F", "unit": "US$/t"},
    "ICE Nature-Based": {"ticker": None, "unit": "US$/t"},
    "California Air Resources Board (ARB) - Allowance": {"ticker": None, "unit": "US$/t"},
    "Australia ACCU": {"ticker": None, "unit": "A$/t"},
}

# ---------------------
# HELPERS: Fetch data
# ---------------------
@st.cache_data(ttl=1800)
def fetch_yfinance(tickers: dict, period_days=30):
    """
    Fetch simple historical OHLCV for a dict name->ticker over the last period_days.
    Returns dict[name] = DataFrame
    """
    period = f"{period_days}d"
    results = {}
    for name, ticker in tickers.items():
        if ticker is None:
            continue
        try:
            df = yf.download(ticker, period=period, interval="1d", progress=False)
            if df is None or df.empty:
                continue
            df = df.dropna(how="all")
            results[name] = df
        except Exception as e:
            # we don't crash on failures: show missing data in UI
            results[name] = None
    return results

def fetch_compliance_placeholder(market_key):
    """
    Placeholder function for compliance markets that are not on Yahoo.
    Replace the internals with a dedicated API call or web-scrape to a reliable provider,
    e.g., CORE Markets, World Bank Carbon Pricing Dashboard, ICE, Nasdaq, or local regulator feeds.
    Return: dict with 'price' (float) and optionally 'history' (pd.Series or DataFrame).
    """
    # DEFAULT: return None/NaN; implement your own fetch here.
    return {"price": None, "history": None, "source_note": "placeholder - wire an API"}

@st.cache_data(ttl=1800)
def fetch_all_data(days):
    # Fetch commodities and FX via yfinance
    commod_data = fetch_yfinance(commodities, period_days=days)
    fx_data = fetch_yfinance(currencies, period_days=days)
    # Fetch compliance: try yfinance tickers where provided, otherwise placeholder API
    compliance_data = {}
    for name, meta in compliance_markets.items():
        tick = meta.get("ticker")
        if tick:
            try:
                df = yf.download(tick, period=f"{days}d", interval="1d", progress=False)
                if df is None or df.empty:
                    compliance_data[name] = {"price": None, "history": None, "unit": meta["unit"], "source_note": f"Ticker {tick} returned empty"}
                else:
                    last_price = df["Close"].iloc[-1]
                    compliance_data[name] = {"price": float(last_price), "history": df, "unit": meta["unit"], "source_note": f"Ticker {tick}"}
            except Exception as e:
                compliance_data[name] = {"price": None, "history": None, "unit": meta["unit"], "source_note": f"Ticker error: {e}"}
        else:
            # Call placeholder / API fetcher (user should replace implementation)
            compliance_data[name] = fetch_compliance_placeholder(name)
            compliance_data[name]["unit"] = meta["unit"]
    return commod_data, fx_data, compliance_data

# ---------------------
# SIDEBAR options
# ---------------------
st.sidebar.header("Settings")
days = st.sidebar.slider("Days of history", 7, 180, 30)
show_sections = {
    "Commodities": st.sidebar.checkbox("Show Commodities", True),
    "FX": st.sidebar.checkbox("Show FX", True),
    "Compliance Carbon": st.sidebar.checkbox("Show Compliance Carbon Markets", True),
}
convert_to = st.sidebar.selectbox("Display compliance prices in (if local currency):", options=["Local currency", "USD"], index=1)
generate_pdf = st.sidebar.checkbox("Enable PDF generation button", True)

# ---------------------
# LOAD DATA
# ---------------------
with st.spinner("Fetching market data..."):
    commod_data, fx_data, compliance_data = fetch_all_data(days)

# Helper: summarize a dict of yfinance DataFrames into a table
def summary_from_yf_dict(d):
    rows = []
    for name, df in d.items():
        if df is None or df.empty:
            rows.append({"Asset": name, "Last Price": None, "Change %": None, "Volume": None})
            continue
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2]) if len(df) > 1 else last
        pct = (last - prev) / prev * 100 if prev != 0 else 0
        vol = int(df["Volume"].iloc[-1]) if "Volume" in df.columns else None
        rows.append({"Asset": name, "Last Price": last, "Change %": round(pct, 2), "Volume": vol})
    return pd.DataFrame(rows)

def compliance_summary_table(compliance_dict, fx_df_for_conv=None, to_usd=False):
    rows = []
    for name, meta in compliance_dict.items():
        price = meta.get("price")
        unit = meta.get("unit", "")
        source = meta.get("source_note", "")
        conv_note = ""
        if to_usd and price is not None:
            # Try to convert from local currency to USD using fx_df_for_conv. This is simplistic:
            # Requires mapping currency -> fx ticker available in fx_data (e.g. NZ$/USD would require USDNZD or NZDUSD)
            # Here we'll implement conversions for a few known currencies (A$, NZ$, KRW, RMB, £) using FX dict
            converted = None
            if "NZ$" in unit:
                # NZD -> USD: use USD/NZD (inverse of USDNOK etc). We have USD/JPY etc.
                # Many FX tickers are quoted as USDXXX=X. To get local->USD we need the correct pair or invert.
                pair = "USD/NZD"  # not in our fx set by default - user should add more fx tickers
                conv_note = "(conversion not available - add USD/NZD pair)"
            elif "A$" in unit or "A$" in name:
                conv_note = "(conversion not available - add USD/AUD pair)"
            elif "KRW" in unit:
                conv_note = "(conversion not available - add USDKRW pair)"
            elif "RMB" in unit or "CNY" in unit:
                # we have USD/CNY = USDCNY=X: price is USD per CNY, so multiply price_in_RMB * (USD per CNY)
                fx_pair = "USD/CNY"
                if fx_pair in fx_data and fx_data[fx_pair] is not None:
                    # last FX value: USD per CNY
                    fx_last = float(fx_data[fx_pair]["Close"].iloc[-1])
                    converted = price * fx_last
                    conv_note = f"converted using {fx_pair}"
            elif "£" in unit:
                # Need GBP/USD to convert GBP -> USD: GBPUSD=X gives USD per GBP
                fx_pair = "GBP/USD"
                if fx_pair in fx_data and fx_data[fx_pair] is not None:
                    fx_last = float(fx_data[fx_pair]["Close"].iloc[-1])
                    converted = price * fx_last
                    conv_note = f"converted using {fx_pair}"
            if converted is not None:
                rows.append({"Market": name, "Unit": unit, "Last Price (local)": price, "Last Price (USD)": round(converted, 4), "Source": source, "Note": conv_note})
            else:
                rows.append({"Market": name, "Unit": unit, "Last Price (local)": price, "Last Price (USD)": None, "Source": source, "Note": conv_note})
        else:
            rows.append({"Market": name, "Unit": unit, "Last Price (local)": price, "Last Price (USD)": None, "Source": source, "Note": ""})
    return pd.DataFrame(rows)

# ---------------------
# DISPLAY: Commodities & FX
# ---------------------
if show_sections["Commodities"]:
    st.subheader("📈 Commodities Overview")
    commod_table = summary_from_yf_dict(commod_data)
    st.dataframe(commod_table, use_container_width=True)

if show_sections["FX"]:
    st.subheader("💱 FX Overview")
    fx_table = summary_from_yf_dict(fx_data)
    st.dataframe(fx_table, use_container_width=True)

# ---------------------
# DISPLAY: Compliance Carbon Markets
# ---------------------
if show_sections["Compliance Carbon"]:
    st.subheader("🌿 Compliance Carbon Markets")
    comp_df = compliance_summary_table(compliance_data, fx_data, to_usd=(convert_to == "USD"))
    st.dataframe(comp_df, use_container_width=True)
    st.markdown("**Notes:** Many compliance markets require dedicated data feeds or scraping from regulator/market websites. Rows labelled `placeholder` or with conversion notes need API wiring.")

# ---------------------
# PLOTS: Mini charts for commodities, FX, compliance history (where available)
# ---------------------
st.subheader("📊 Mini Price Trends")
cols = st.columns(3)

# Helper to plot a series into a column
def plot_series_in_col(col, name, df, ylabel=None):
    fig, ax = plt.subplots(figsize=(5,2.4))
    ax.plot(df.index, df["Close"], linewidth=1)
    ax.set_title(name, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8)
    ax.grid(True, linestyle=":", linewidth=0.5)
    col.pyplot(fig)
    plt.close(fig)
    return fig

# Plot a few commodities
i = 0
for name, df in commod_data.items():
    if df is None or df.empty: continue
    plot_series_in_col(cols[i%3], name, df)
    i += 1
    if i >= 9:
        break

# Plot a few FX pairs
i = 0
for name, df in fx_data.items():
    if df is None or df.empty: continue
    plot_series_in_col(cols[i%3], name, df, ylabel="Rate")
    i += 1
    if i >= 6:
        break

# Plot compliance histories if present
i = 0
for name, meta in compliance_data.items():
    hist = meta.get("history")
    if hist is None or isinstance(hist, (float,int)) or hist is None:
        continue
    plot_series_in_col(cols[i%3], name, hist, ylabel=meta.get("unit", ""))
    i += 1
    if i >= 6:
        break

# ---------------------
# PDF EXPORT: generate PDF snapshot
# ---------------------
def generate_pdf_snapshot(commod_table, fx_table, comp_table, commod_data, fx_data, compliance_data, days):
    """
    Generate a multipage PDF with summary tables and mini charts.
    """
    buf = io.BytesIO()
    now = datetime.utcnow().strftime("%Y-%m-%d_%H%MUTC")
    with PdfPages(buf) as pdf:
        # Title page
        fig_title = plt.figure(figsize=(11,8.5))
        fig_title.text(0.5, 0.6, "Commodities, FX & Compliance Carbon - Daily Snapshot", ha='center', va='center', fontsize=20)
        fig_title.text(0.5, 0.52, f"Generated: {now} (UTC) • History: last {days} days", ha='center', va='center', fontsize=10)
        pdf.savefig(fig_title)
        plt.close(fig_title)

        # Commodities table page
        fig1, ax1 = plt.subplots(figsize=(11,8.5))
        ax1.axis('off')
        ax1.set_title("Commodities Summary", fontsize=14)
        # render pandas table into matplotlib
        tbl = ax1.table(cellText=commod_table.fillna("").values, colLabels=commod_table.columns, loc='center', cellLoc='center')
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.scale(1, 1.2)
        pdf.savefig(fig1)
        plt.close(fig1)

        # FX table page
        fig2, ax2 = plt.subplots(figsize=(11,8.5))
        ax2.axis('off')
        ax2.set_title("FX Summary", fontsize=14)
        tbl2 = ax2.table(cellText=fx_table.fillna("").values, colLabels=fx_table.columns, loc='center', cellLoc='center')
        tbl2.auto_set_font_size(False)
        tbl2.set_fontsize(9)
        tbl2.scale(1, 1.2)
        pdf.savefig(fig2)
        plt.close(fig2)

        # Compliance table page
        fig3, ax3 = plt.subplots(figsize=(11,8.5))
        ax3.axis('off')
        ax3.set_title("Compliance Carbon Markets Summary", fontsize=14)
        tbl3 = ax3.table(cellText=comp_table.fillna("").values, colLabels=comp_table.columns, loc='center', cellLoc='center')
        tbl3.auto_set_font_size(False)
        tbl3.set_fontsize(9)
        tbl3.scale(1, 1.2)
        pdf.savefig(fig3)
        plt.close(fig3)

        # Add mini charts: loop through a selection
        def add_series_page(title, series_dict, max_plots=6):
            plotted = 0
            for name, df in series_dict.items():
                if df is None or getattr(df, "empty", True): continue
                fig, ax = plt.subplots(figsize=(11,8.5))
                ax.plot(df.index, df["Close"], linewidth=1)
                ax.set_title(f"{title} — {name}")
                ax.grid(True, linestyle=":", linewidth=0.5)
                pdf.savefig(fig)
                plt.close(fig)
                plotted += 1
                if plotted >= max_plots:
                    break
            return plotted

        add_series_page("Commodities Trend", commod_data, max_plots=6)
        add_series_page("FX Trend", fx_data, max_plots=6)

        # Compliance trend pages (if any history)
        # Build a dict of histories
        hist_dict = {}
        for name, meta in compliance_data.items():
            hist = meta.get("history")
            if isinstance(hist, pd.DataFrame) and not hist.empty:
                hist_dict[name] = hist
        if hist_dict:
            add_series_page("Compliance Market Trends", hist_dict, max_plots=6)

        # Final page: disclaimer / notes
        fig_end = plt.figure(figsize=(11,8.5))
        fig_end.text(0.02, 0.95, "Notes & Data Sources", fontsize=12, weight='bold')
        y = 0.9
        notes = [
            "Data sources: Yahoo Finance (where available), placeholders for markets that require dedicated APIs or scraping.",
            "Markets with 'None' prices are placeholders. Replace fetch_compliance_placeholder() with real API/scrapes.",
            "Currency conversions are simplistic and require robust FX pairs for precise conversions.",
            "This PDF was generated by the Streamlit dashboard (v4)."
        ]
        for n in notes:
            fig_end.text(0.02, y, f"- {n}", fontsize=9)
            y -= 0.05
        pdf.savefig(fig_end)
        plt.close(fig_end)

        # finalize
        pdf.close()

    buf.seek(0)
    return buf

# Show the PDF generation button if enabled
if generate_pdf:
    if st.button("📄 Generate PDF Summary"):
        with st.spinner("Generating PDF..."):
            comp_table_for_pdf = compliance_summary_table(compliance_data, fx_data, to_usd=(convert_to=="USD"))
            commod_table_for_pdf = summary_from_yf_dict(commod_data)
            fx_table_for_pdf = summary_from_yf_dict(fx_data)
            pdf_buf = generate_pdf_snapshot(commod_table_for_pdf, fx_table_for_pdf, comp_table_for_pdf, commod_data, fx_data, compliance_data, days)
            # Offer download
            st.success("PDF generated — click to download")
            st.download_button(
                label="⬇️ Download PDF snapshot",
                data=pdf_buf,
                file_name=f"market_snapshot_{datetime.utcnow().strftime('%Y%m%d_%H%MUTC')}.pdf",
                mime="application/pdf"
            )

# ---------------------
# USAGE NOTES / NEXT STEPS
# ---------------------
st.markdown("### Next steps / How to wire real compliance feeds")
st.markdown("""
1. Replace `fetch_compliance_placeholder()` with dedicated fetchers:
   - CORE Markets (ACCU, NZ ETS), ICE/CBL (GEO, NGO), EU ETS (World Bank or ICE), CARB (California data feed), RGGI portal, K-ETS official feed, China registry.
2. For currency conversion of local units to USD, add the required FX pairs (e.g., USD/NZD, USD/KRW, USD/AUD) to the `currencies` dict and fetch them.
3. If you need authenticated APIs, store credentials in environment variables and call them from the placeholder fetch function.
4. Improve PDF layout using reportlab or wkhtmltopdf if you want an HTML-styled report (requires external binary).
""")
