import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Benchmark symbol in Yahoo Finance (Nifty 500 / Nifty 50 fallback)
BENCHMARK_TICKERS = ["^CRSLDX", "^NSEI"]

def get_all_nse_tickers():
    """
    Dynamically fetch the entire NSE Equity Universe:
    Nifty 500 + Nifty Smallcap 250 + Nifty Microcap 250 (1,000+ stocks).
    """
    urls = [
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftysmallcap250_list.csv"
    ]
    all_symbols = set()
    
    for url in urls:
        try:
            df = pd.read_csv(url)
            if 'Symbol' in df.columns:
                symbols = df['Symbol'].dropna().astype(str).str.strip().tolist()
                all_symbols.update(symbols)
        except Exception:
            continue
            
    if all_symbols:
        tickers = [f"{sym}.NS" for sym in sorted(all_symbols)]
        print(f"Dynamically fetched {len(tickers)} liquid stock symbols across the entire NSE Market!")
        return tickers
    else:
        print("Warning: Could not fetch live NSE index lists. Using fallback list.")
        return [
            "CUPID.NS", "AEGISLOG.NS", "PARAS.NS", "BDL.NS", "MTARTECH.NS", "NETWEB.NS", "BEPL.NS",
            "HAL.NS", "BEL.NS", "MAZDOCK.NS", "COCHINSHIP.NS", "RVNL.NS", "IRFC.NS",
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
            "INFY.NS", "LT.NS", "M&M.NS", "TRENT.NS", "VBL.NS", "POLYCAB.NS", "DIXON.NS",
            "COALINDIA.NS", "SUZLON.NS", "KALYANKJIL.NS", "PERSISTENT.NS", "COFORGE.NS",
            "KPITTECH.NS", "OFSS.NS", "DELHIVERY.NS", "POLICYBZR.NS", "POONAWALLA.NS",
            "CHOLAFIN.NS", "MAXHEALTH.NS", "MANKIND.NS", "LUPIN.NS", "TORNTPHARM.NS",
            "TVSMOTOR.NS", "SOLARINDS.NS", "KEI.NS", "APARINDS.NS", "BSE.NS", "CDSL.NS",
            "MCX.NS", "ANGELONE.NS", "EMUDHRA.NS", "TITAN.NS", "NTPC.NS", "POWERGRID.NS"
        ]

def run_two_filters_screener():
    print("Fetching Benchmark Data (Nifty 500)...")
    nifty_60d_ret = 0.0
    for b_ticker in BENCHMARK_TICKERS:
        try:
            nifty = yf.download(b_ticker, period="6mo", progress=False)
            if not nifty.empty and len(nifty) >= 60:
                nifty_close = nifty['Close'][b_ticker] if isinstance(nifty.columns, pd.MultiIndex) else nifty['Close']
                nifty_60d_ret = float((nifty_close.iloc[-1] - nifty_close.iloc[-60]) / nifty_close.iloc[-60] * 100)
                print(f"Using {b_ticker} as benchmark. 60-day return: {nifty_60d_ret:.2f}%")
                break
        except Exception:
            continue

    tickers = get_all_nse_tickers()
    print(f"\nScreening entire universe of {len(tickers)} NSE stocks (Two Filters Screener)...")
    results = []

    for idx, ticker in enumerate(tickers, start=1):
        try:
            df = yf.download(ticker, period="6mo", progress=False)
            if df.empty or len(df) < 60:
                continue

            close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
            high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
            low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
            volume = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']

            curr_price = float(close.iloc[-1])

            # FILTER 1: Prior Move Strength (60-day % gain)
            move_60d = float((curr_price - close.iloc[-60]) / close.iloc[-60] * 100)

            # Informational: Proximity to 60-Day High (% below 60D High)
            high_60d = float(high.iloc[-60:].max())
            prox_to_high = float((high_60d - curr_price) / high_60d * 100)

            # FILTER 2: Relative Strength vs Benchmark (Outperformance Score)
            rs_score = move_60d - nifty_60d_ret

            # Additional Indicators: ADR% (Average Daily Range over last 20 days)
            daily_range = (high - low) / low * 100
            adr_20 = float(daily_range.iloc[-20:].mean())

            # Tightness Check: Range over last 5 days
            tight_5d_range = float((high.iloc[-5:].max() - low.iloc[-5:].min()) / low.iloc[-5:].min() * 100)

            # Volume Ratio: Last day volume vs 20-day average volume
            vol_ratio = float(volume.iloc[-1] / volume.iloc[-20:].mean())

            # 2-Filter Screener Criteria (Filter 1 + Filter 2 + ADR >= 2.0%)
            passes_screener = (move_60d >= 15.0) and (rs_score > 0) and (adr_20 >= 2.0)

            results.append({
                "Symbol": ticker.replace(".NS", ""),
                "Price (Rs)": round(curr_price, 2),
                "Filter 1: 60D Move (%)": round(move_60d, 2),
                "Filter 2: RS vs Nifty (%)": round(rs_score, 2),
                "Dist to Pivot (%)": round(prox_to_high, 2),
                "ADR 20D (%)": round(adr_20, 2),
                "5D Tightness (%)": round(tight_5d_range, 2),
                "Vol Ratio": round(vol_ratio, 2),
                "Status": "TOP FOCUS" if passes_screener else "Watchlist"
            })
        except Exception:
            continue

    if not results:
        print("No stock data returned.")
        return

    # Convert to DataFrame & Sort by Status, RS Score
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by=["Status", "Filter 2: RS vs Nifty (%)"], 
                                       ascending=[False, False])

    # Generate timestamped filenames
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"Two_Filters_Breakouts_{now_str}.xlsx"
    csv_filename = f"Two_Filters_Breakouts_{now_str}.csv"

    df_results.to_excel(excel_filename, index=False)
    df_results.to_csv(csv_filename, index=False)
    
    print(f"\nScreening complete! Processed {len(results)} stocks.")
    print(f" Saved Excel: {excel_filename}")
    print(f" Saved CSV:   {csv_filename}")
    
    # Display TOP FOCUS Stocks in terminal
    print("\n--- TWO FILTERS TOP FOCUS CANDIDATES ---")
    top_candidates = df_results[df_results["Status"] == "TOP FOCUS"].head(15)
    if not top_candidates.empty:
        print(top_candidates.to_string(index=False))
    else:
        print("No stocks passed thresholds. Displaying top candidates by RS:")
        print(df_results.head(15).to_string(index=False))

if __name__ == "__main__":
    run_two_filters_screener()
