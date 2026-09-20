import urllib.request
import json
import csv
import io
import datetime
import ssl
import sys
import os
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

# Global SSL Context fix for urllib on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

UNIVERSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 30.0            # Minimum price in INR
MIN_AVG_VOLUME = 75000       # Minimum 20-day average daily volume
MIN_AVG_TURNOVER = 10000000  # Minimum 1 Crore INR daily turnover
NUM_THREADS = 40             # Thread pool for fast downloading

# Comprehensive Liquid NSE Equities Fallback List (~120 High Liquidity & Growth Stocks)
FALLBACK_NSE_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "BHARTIARTL.NS", "ITC.NS",
    "SBIN.NS", "LTIM.NS", "LT.NS", "HCLTECH.NS", "AXISBANK.NS", "KOTAKBANK.NS", "TATAMOTORS.NS",
    "SUNPHARMA.NS", "MARUTI.NS", "NTPC.NS", "TITAN.NS", "ULTRACEMCO.NS", "ADANIENT.NS", "ONGC.NS",
    "TATASTEEL.NS", "POWERGRID.NS", "M&M.NS", "BAJFINANCE.NS", "JSWSTEEL.NS", "COALINDIA.NS",
    "ASIANPAINT.NS", "ADANIPORTS.NS", "BPCL.NS", "BHAL.NS", "SIEMENS.NS", "BEL.NS", "HAL.NS",
    "DIXON.NS", "POLYCAB.NS", "PERSISTENT.NS", "TATAELXSI.NS", "KAYNES.NS", "DATAPATTNS.NS",
    "MAZDOCK.NS", "COCHINSHIP.NS", "GRSE.NS", "BEML.NS", "BALUFORGE.NS", "AURIONPRO.NS",
    "BBOX.NS", "AEGISLOG.NS", "CEMPRO.NS", "BHAGYANGR.NS", "ASHOKA.NS", "BAJAJCON.NS", "BSOFT.NS",
    "CHOLAFIN.NS", "CHOLAHLDNG.NS", "ABB.NS", "MARKSANS.NS", "DREDGECORP.NS", "MANORAMA.NS",
    "OFSS.NS", "CARTRADE.NS", "MPSLTD.NS", "NYKAA.NS", "ZOMATO.NS", "POLICYBZR.NS", "PAYTM.NS",
    "TRENT.NS", "CGPOWER.NS", "APARINDS.NS", "SUZLON.NS", "PRESTIGE.NS", "OBEROIRLTY.NS",
    "PHOENIXLTD.NS", "GODREJPROP.NS", "LODHA.NS", "MAXHEALTH.NS", "MEDANTA.NS", "NH.NS",
    "MANKIND.NS", "JBCHEPHARM.NS", "GLENMARK.NS", "TORNTPHARM.NS", "LUPIN.NS", "AUROPHARMA.NS",
    "TATAINVEST.NS", "POONAWALLA.NS", "MUTHOOTFIN.NS", "MANAPPURAM.NS", "REC.NS", "PFC.NS",
    "IREDA.NS", "HUDCO.NS", "RVNL.NS", "IRFC.NS", "RAILTEL.NS", "CONCOR.NS", "TITAGARH.NS",
    "TEXRAIL.NS", "HINDALCO.NS", "NATIONALUM.NS", "VEDL.NS", "NMDC.NS", "GPIL.NS", "JINDALSTEL.NS"
]

def fetch_nse_universe():
    """Fetch active equity symbols from NSE archives or fallback."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(UNIVERSE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
            content = response.read().decode('utf-8')
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        header_lower = [h.strip().lower() for h in header]
        symbol_idx = header_lower.index("symbol")
        series_idx = header_lower.index("series") if "series" in header_lower else -1

        tickers = []
        for row in reader:
            if not row or len(row) <= symbol_idx:
                continue
            symbol = row[symbol_idx].strip()
            if series_idx != -1:
                series = row[series_idx].strip()
                if series not in ["EQ", "BE", "SM", "ST"]:
                    continue
            tickers.append(symbol + ".NS")

        if len(tickers) > 200:
            print(f"[+] Successfully loaded {len(tickers)} active equity tickers from NSE archives.")
            return tickers
    except Exception as e:
        print(f"[!] Warning: Could not fetch NSE official CSV ({e}). Using robust liquid fallback list.")

    print(f"[+] Loaded {len(FALLBACK_NSE_UNIVERSE)} liquid NSE tickers from fallback list.")
    return FALLBACK_NSE_UNIVERSE

def fetch_chart_data(ticker, period="1y"):
    """Fetch daily OHLCV data from Yahoo Finance API for a given ticker."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as response:
            res_data = json.loads(response.read().decode('utf-8'))
        chart_result = res_data.get('chart', {}).get('result', [])
        if not chart_result:
            return ticker, None
        result = chart_result[0]
        timestamps = result.get('timestamp', [])
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        opens = quote.get('open', [])
        highs = quote.get('high', [])
        lows = quote.get('low', [])
        closes = quote.get('close', [])
        volumes = quote.get('volume', [])

        clean_data = []
        for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
            if t and o is not None and h is not None and l is not None and c is not None and v is not None:
                o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)
                if h >= o and h >= c and l <= o and l <= c and h >= l and v >= 0:
                    clean_data.append({
                        'date': datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d'),
                        'open': o, 'high': h, 'low': l, 'close': c, 'volume': v
                    })
        return ticker, clean_data
    except Exception:
        return ticker, None

def calculate_indicators(data):
    """Calculate moving averages, ADR%, Relative Strength, and Breakout parameters."""
    df = pd.DataFrame(data)
    if len(df) < 50:
        return None

    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['sma50'] = df['close'].rolling(window=50).mean()
    df['sma200'] = df['close'].rolling(window=min(200, len(df))).mean()

    # 20-day Average Daily Range Percentage (ADR%)
    df['daily_range_pct'] = ((df['high'] - df['low']) / df['close']) * 100.0
    df['adr20'] = df['daily_range_pct'].rolling(window=20).mean()

    # 20-day Average Volume & Turnover
    df['vol20'] = df['volume'].rolling(window=20).mean()
    df['turnover20'] = df['close'] * df['vol20']

    # 52-Week High (up to 252 sessions)
    lookback_52w = min(252, len(df))
    df['high_52w'] = df['high'].rolling(window=lookback_52w).max()

    return df

def score_stock_qullamaggie(df, nifty_returns):
    """
    Score stock based on the 12-point Qullamaggie Breakout Checklist.
    Returns score (0-12), Grade (A*, A, B, Fail), and detail dictionary.
    """
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    n_bars = len(df)

    close = curr['close']
    ema10 = curr['ema10']
    ema21 = curr['ema21']
    sma50 = curr['sma50']
    sma200 = curr['sma200']
    adr20 = curr['adr20']
    vol20 = curr['vol20']
    turnover20 = curr['turnover20']
    high_52w = curr['high_52w']

    # Basic Liquidity Filters
    if close < MIN_PRICE or vol20 < MIN_AVG_VOLUME or turnover20 < MIN_AVG_TURNOVER:
        return None

    checklist = {}

    # 1. Is stock above all key daily moving averages? (10 EMA, 21 EMA, 50 SMA, 200 SMA)
    c1 = (close > ema10) and (close > ema21) and (close > sma50) and (close > sma200)
    checklist['1_above_all_mas'] = c1

    # 2. Daily Relative Strength vs Nifty 50 (20-day performance outperforming Nifty)
    stock_20d_ret = ((close - df.iloc[-20]['close']) / df.iloc[-20]['close']) * 100.0 if n_bars >= 20 else 0.0
    nifty_20d_ret = nifty_returns.get('20d', 0.0)
    c2 = stock_20d_ret > nifty_20d_ret
    checklist['2_rs_daily'] = c2

    # 3. Technical Position Relative to Yesterday (Strong Close near High of Day)
    day_range = curr['high'] - curr['low']
    close_pos = (close - curr['low']) / day_range if day_range > 0 else 0.5
    c3 = (close_pos >= 0.50) and (close >= prev['close'] * 0.995)
    checklist['3_strong_tech_pos'] = c3

    # 4. Intraday / Flag Consolidation Tightness (Recent 3-day range tight relative to ADR)
    recent_3d_range = max(df.iloc[-3:]['high']) - min(df.iloc[-3:]['low'])
    recent_3d_pct = (recent_3d_range / close) * 100.0
    c4 = recent_3d_pct <= (1.2 * adr20)
    checklist['4_tight_consolidation'] = c4

    # 5. Clean Trend Structure (Holding above 21 EMA continuously for last 5 sessions)
    c5 = all(df.iloc[-5:]['close'] > df.iloc[-5:]['ema21'])
    checklist['5_clean_structure'] = c5

    # 6. Group / Momentum Sector (Outperforming benchmark overall over 60 days)
    stock_60d_ret = ((close - df.iloc[-min(60, n_bars)]['close']) / df.iloc[-min(60, n_bars)]['close']) * 100.0
    nifty_60d_ret = nifty_returns.get('60d', 0.0)
    c6 = stock_60d_ret > (nifty_60d_ret + 5.0)
    checklist['6_group_momentum'] = c6

    # 7. Strong Momentum Leader (1-Month gain >= 10% or 3-Month gain >= 20%)
    stock_30d_ret = ((close - df.iloc[-min(30, n_bars)]['close']) / df.iloc[-min(30, n_bars)]['close']) * 100.0
    c7 = (stock_30d_ret >= 8.0) or (stock_60d_ret >= 18.0)
    checklist['7_leader_momentum'] = c7

    # 8. Distance to 10-day EMA <= 1.0x 20-day ADR% (CRITICAL QULLAMAGGIE RULE: Not Overextended!)
    dist_10ema_pct = ((close - ema10) / ema10) * 100.0
    c8 = (dist_10ema_pct <= (1.0 * adr20)) and (dist_10ema_pct >= -1.0)
    checklist['8_not_extended_10ema'] = c8

    # 9. Prior Character of High ADR% (Explosive Movement Potential: ADR20% >= 3.0%)
    c9 = adr20 >= 3.0
    checklist['9_high_adr_character'] = c9

    # 10. Clear Runway / Proximity to 52-Week High (Within 12% of 52-Wk High)
    dist_52w_high_pct = ((high_52w - close) / high_52w) * 100.0
    c10 = dist_52w_high_pct <= 12.0
    checklist['10_clear_runway_52w'] = c10

    # 11. Volume Contraction / Building Demand (Volume dry up or higher volume on green days)
    recent_green_vol = df.iloc[-10:][df.iloc[-10:]['close'] >= df.iloc[-10:]['open']]['volume'].sum()
    recent_red_vol = df.iloc[-10:][df.iloc[-10:]['close'] < df.iloc[-10:]['open']]['volume'].sum()
    c11 = recent_green_vol >= recent_red_vol
    checklist['11_volume_demand'] = c11

    # 12. Primed Near Breakout Pivot (Close within 3.5% of 10-day High - ready for tomorrow's ORB!)
    high_10d = df.iloc[-10:]['high'].max()
    dist_10d_high = ((high_10d - close) / close) * 100.0
    c12 = dist_10d_high <= 3.5
    checklist['12_near_breakout_pivot'] = c12

    score = sum(1 for val in checklist.values() if val)

    # Grade assignment
    if score >= 11:
        grade = "A*"
    elif score == 10:
        grade = "A"
    elif score == 9:
        grade = "B"
    else:
        grade = "FAIL"

    pivot_high = max(high_10d, high_52w) if dist_52w_high_pct <= 5.0 else high_10d

    details = {
        'score': score,
        'grade': grade,
        'close': round(close, 2),
        'ema10': round(ema10, 2),
        'ema21': round(ema21, 2),
        'adr20_pct': round(adr20, 2),
        'dist_10ema_pct': round(dist_10ema_pct, 2),
        'dist_52w_high_pct': round(dist_52w_high_pct, 2),
        'pivot_high': round(pivot_high, 2),
        'ret_20d_pct': round(stock_20d_ret, 2),
        'ret_60d_pct': round(stock_60d_ret, 2),
        'vol20_avg': int(vol20),
        'checklist': checklist
    }

    return details

def run_screener():
    print("=" * 80)
    print("      NSE TOMORROW BREAKOUT SCREENER (QULLAMAGGIE 12-POINT CHECKLIST)     ")
    print("=" * 80)
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n")

    # Step 1: Download Nifty 50 Index Data for Benchmark Relative Strength
    print("[1/3] Downloading NIFTY 50 (^NSEI) benchmark data...", flush=True)
    _, nifty_data = fetch_chart_data("^NSEI", period="1y")
    nifty_returns = {'20d': 0.0, '60d': 0.0}
    if nifty_data and len(nifty_data) >= 60:
        n_c = nifty_data[-1]['close']
        n_20 = nifty_data[-20]['close']
        n_60 = nifty_data[-60]['close']
        nifty_returns['20d'] = ((n_c - n_20) / n_20) * 100.0
        nifty_returns['60d'] = ((n_c - n_60) / n_60) * 100.0
        print(f"      [NIFTY 50] 20-Day Return: {nifty_returns['20d']:+.2f}%, 60-Day Return: {nifty_returns['60d']:+.2f}%\n")

    # Step 2: Fetch NSE Ticker Universe
    universe = fetch_nse_universe()
    print(f"[2/3] Downloading OHLCV chart data for {len(universe)} NSE tickers using {NUM_THREADS} threads...", flush=True)

    stock_map = {}
    completed = 0
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_chart_data, ticker): ticker for ticker in universe}
        for future in as_completed(futures):
            completed += 1
            if completed % 300 == 0 or completed == len(universe):
                print(f"      Progress: {completed}/{len(universe)} stocks downloaded...", flush=True)
            t, data = future.result()
            if data and len(data) >= 50:
                stock_map[t] = data

    print(f"\n[3/3] Running 12-Point Qullamaggie Breakout Scoring Engine...", flush=True)

    results = []
    for ticker, data in stock_map.items():
        df = calculate_indicators(data)
        if df is None:
            continue

        res = score_stock_qullamaggie(df, nifty_returns)
        if res is not None and res['grade'] != "FAIL":
            clean_symbol = ticker.replace(".NS", "")
            res['symbol'] = clean_symbol
            res['ticker'] = ticker
            results.append(res)

    # Sort results by Score (Descending), then Grade, then proximity to 10 EMA
    results.sort(key=lambda x: (x['score'], -abs(x['dist_10ema_pct']), x['ret_20d_pct']), reverse=True)

    # Output Presentation
    print("\n" + "=" * 110)
    print(f"   BREAKOUT CANDIDATES FOR TOMORROW'S TRADING (TOP ACTIONABLE LIST)")
    print("=" * 110)
    print(f"{'SYMBOL':<14} | {'GRADE':<5} | {'SCORE':<5} | {'LTP (INR)':<10} | {'PIVOT (INR)':<11} | {'10EMA (INR)':<11} | {'ADR(20)%':<8} | {'DIST 10EMA':<10} | {'DIST 52WH':<10} | {'20D RET%':<8}")
    print("-" * 110)

    formatted_rows = []
    for r in results:
        sym = r['symbol']
        grd = r['grade']
        sc = f"{r['score']}/12"
        ltp = f"{r['close']:.2f}"
        piv = f"{r['pivot_high']:.2f}"
        ema10 = f"{r['ema10']:.2f}"
        adr = f"{r['adr20_pct']:.2f}%"
        d10 = f"{r['dist_10ema_pct']:+.2f}%"
        d52 = f"{r['dist_52w_high_pct']:.2f}%"
        r20 = f"{r['ret_20d_pct']:+.2f}%"

        print(f"{sym:<14} | {grd:<5} | {sc:<5} | {ltp:<9} | {piv:<9} | {ema10:<9} | {adr:<8} | {d10:<10} | {d52:<10} | {r20:<8}")

        formatted_rows.append({
            'Symbol': sym,
            'Grade': grd,
            'Score': r['score'],
            'LTP_INR': r['close'],
            'Breakout_Pivot_INR': r['pivot_high'],
            'EMA10_INR': r['ema10'],
            'EMA21_INR': r['ema21'],
            'ADR20_Pct': r['adr20_pct'],
            'Dist_10EMA_Pct': r['dist_10ema_pct'],
            'Dist_52W_High_Pct': r['dist_52w_high_pct'],
            'Return_20D_Pct': r['ret_20d_pct'],
            'Return_60D_Pct': r['ret_60d_pct'],
            'Vol20_Avg': r['vol20_avg']
        })

    print("-" * 110)

    # Save outputs to CSV and JSON
    csv_file = "nse_tomorrow_breakout_candidates.csv"
    json_file = "nse_tomorrow_breakout_candidates.json"

    if formatted_rows:
        df_out = pd.DataFrame(formatted_rows)
        df_out.to_csv(csv_file, index=False)
        with open(json_file, "w") as f:
            json.dump(formatted_rows, f, indent=2)

        print(f"\n[✓] Results successfully exported to:")
        print(f"    - CSV:  {os.path.abspath(csv_file)}")
        print(f"    - JSON: {os.path.abspath(json_file)}")
        print(f"    Total qualified breakout candidates found: {len(formatted_rows)}")
    else:
        print("\n[!] No stocks met the strict 9+/12 threshold today. Market may be extended or consolidating.")

    print("\n" + "=" * 110)
    print(" TRADING PLAN FOR TOMORROW:")
    print(" 1. Focus on A* (11-12/12) and A (10/12) stocks.")
    print(" 2. Mark the 5-Minute Opening Range Breakout (ORB) High at 9:20 AM IST tomorrow.")
    print(" 3. Entry trigger: Clean momentum push through the 5-Min ORB High.")
    print(" 4. Initial Stop Loss: Low of Day (LOD) or Low of 5-Min ORB candle.")
    print("=" * 110 + "\n")

if __name__ == "__main__":
    run_screener()
