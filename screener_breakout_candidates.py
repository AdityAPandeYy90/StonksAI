import urllib.request
import json
import csv
import io
import datetime
import ssl
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Global SSL Context fix for Windows python urllib
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

UNIVERSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 50.0
MIN_VOLUME_AVG = 100000
NUM_THREADS = 50

FALLBACK_NSE_UNIVERSE = [
    "AURIONPRO.NS", "CLSEL.NS", "BEML.NS", "HAL.NS", "MAZDOCK.NS", "BALUFORGE.NS", 
    "BBOX.NS", "AEGISLOG.NS", "CEMPRO.NS", "BHAGYANGR.NS", "BETA.NS", "ASHOKA.NS",
    "BAJAJCON.NS", "BSOFT.NS", "CHOLAFIN.NS", "CHOLAHLDNG.NS", "BANSWRAS.NS", "ABB.NS",
    "TATAELXSI.NS", "POLYCAB.NS", "PERSISTENT.NS", "DIXON.NS", "KAYNES.NS", "DATAPATTNS.NS",
    "APEX.NS", "TARSONS.NS", "XTRANET.NS", "AVTNPL.NS", "PRAKASH.NS", "RGL.NS", "JNKINDIA.NS",
    "MARKSANS.NS", "LGEINDIA.NS", "DREDGECORP.NS", "MOL.NS", "VSSL.NS", "MANORAMA.NS"
]

def fetch_nse_tickers():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(UNIVERSE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as response:
            content = response.read().decode('utf-8')
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        symbol_idx = [h.strip().lower() for h in header].index("symbol")
        series_idx = [h.strip().lower() for h in header].index("series") if "series" in [h.strip().lower() for h in header] else -1
        
        tickers = []
        for row in reader:
            if not row:
                continue
            symbol = row[symbol_idx].strip()
            if series_idx != -1:
                series = row[series_idx].strip()
                if series not in ["EQ", "BE", "SM", "ST"]:
                    continue
            tickers.append(symbol + ".NS")
            
        if tickers and len(tickers) > 200:
            print(f"Loaded {len(tickers)} active equity tickers from NSE archives.")
            return tickers
    except Exception:
        pass
    print("Using liquid fallback universe list.")
    return FALLBACK_NSE_UNIVERSE

def fetch_stock_chart_data(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d"
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
        clean_data = [{'date': datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d'), 'open': float(o), 'high': float(h), 'low': float(l), 'close': float(c), 'volume': int(v)} for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes) if t and o and h and l and c and v]
        return ticker, clean_data
    except Exception:
        return ticker, None

def run_screener(target_date_str=None):
    sample_tickers = fetch_nse_tickers()
    
    print(f"\n[1/3] Downloading latest OHLCV data for {len(sample_tickers)} liquid NSE stocks using {NUM_THREADS} worker threads...", flush=True)
    stock_data_map = {}
    completed_cnt = 0
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_stock_chart_data, t): t for t in sample_tickers}
        for future in as_completed(futures):
            completed_cnt += 1
            if completed_cnt % 500 == 0:
                print(f"Downloaded {completed_cnt}/{len(sample_tickers)} stocks...", flush=True)
            t, clean_data = future.result()
            if clean_data and len(clean_data) > 30:
                stock_data_map[t] = clean_data

    # Determine Target Date
    all_dates_set = set()
    for t, data in stock_data_map.items():
        for item in data:
            all_dates_set.add(item['date'])
    sorted_dates = sorted(list(all_dates_set))
    
    if not sorted_dates:
        print("[ERROR] Could not fetch market dates. Please check internet connection.", flush=True)
        return

    if not target_date_str or target_date_str.strip() == "":
        target_date = sorted_dates[-1]
    else:
        target_date = target_date_str.strip()
        if target_date not in sorted_dates:
            closest = min(sorted_dates, key=lambda d: abs((datetime.datetime.strptime(d, '%Y-%m-%d') - datetime.datetime.strptime(target_date, '%Y-%m-%d')).days))
            print(f"[WARNING] Target date '{target_date}' not found in calendar. Using closest trading day: '{closest}'", flush=True)
            target_date = closest
            
    date_idx_map = {d: i for i, d in enumerate(sorted_dates)}
    target_idx = date_idx_map[target_date]
    
    print(f"\n==========================================================================", flush=True)
    print(f"       FULL NSE EXCHANGE BREAKOUT SCREENER RESULTS FOR DATE: {target_date} ", flush=True)
    print(f"==========================================================================", flush=True)

    # EXACT BACKTEST CODE LOGIC FOR CANDIDATE SELECTION
    step2_candidates = []

    for t, data in stock_data_map.items():
        hist = {date_idx_map[item['date']]: item for item in data if item['date'] in date_idx_map}
        if target_idx not in hist or (target_idx - 1) not in hist:
            continue
            
        curr = hist[target_idx]
        prev = hist[target_idx - 1]
        
        # Liquidity Check (Price >= 50, 20-Day Avg Vol >= 100,000)
        vol_sum = sum(hist[v_idx]['volume'] for v_idx in range(max(0, target_idx - 19), target_idx + 1) if v_idx in hist)
        vol_cnt = sum(1 for v_idx in range(max(0, target_idx - 19), target_idx + 1) if v_idx in hist)
        avg_vol_20 = vol_sum / vol_cnt if vol_cnt > 0 else 0
        
        if curr['close'] < MIN_PRICE or avg_vol_20 < MIN_VOLUME_AVG:
            continue
            
        chg_pct = (curr['close'] / prev['close'] - 1) * 100
        
        # EXACT BACKTEST TRIGGER: Today's Price Change >= +4.0%
        if chg_pct >= 4.0:
            # EXACT BACKTEST PRIOR 3-MONTH MOMENTUM SCORE (60 trading days prior to prev close)
            prior_3m_gain = (prev['close'] / hist[target_idx - 60]['close'] - 1) * 100 if (target_idx - 60) in hist else 0.0
            vol_ratio = (curr['volume'] / avg_vol_20) if avg_vol_20 > 0 else 0.0
            clean_ticker = t.replace('.NS', '')
            
            step2_candidates.append({
                'ticker': clean_ticker,
                'close': curr['close'],
                'chg_pct': chg_pct,
                'vol_ratio': vol_ratio,
                'prior_3m': prior_3m_gain,
                'orb_entry': curr['close'] * 1.015, # estimated ORB entry for next day
                'lod_stop': curr['low']            # estimated LoD stop for next day
            })

    # STEP 2 DISPLAY: Sort by Today's Breakout Gain %
    step2_display = sorted(step2_candidates, key=lambda x: x['chg_pct'], reverse=True)
    
    # STEP 3 DISPLAY: EXACT BACKTEST CODE RANKING (Sorted by Prior 3-Month Momentum Leaderboard)
    step3_candidates = sorted(step2_candidates, key=lambda x: x['prior_3m'], reverse=True)

    print(f"\n--------------------------------------------------------------------------", flush=True)
    print(f" STEP 2 OUTPUT: ALL +4% BREAKOUT STOCKS ON {target_date} ({len(step2_display)} Stocks Found)", flush=True)
    print(f"--------------------------------------------------------------------------", flush=True)
    if not step2_display:
        print("  No +4% breakout stocks found on this date.", flush=True)
    else:
        print(f"{'Ticker':<12} | {'Close (Rs)':<10} | {'Day Gain (%)':<12} | {'Vol Surge':<10} | {'Prior 3M Move':<12}", flush=True)
        print(f"-"*65, flush=True)
        for s in step2_display[:30]:  # Display top 30
            print(f"{s['ticker']:<12} | Rs. {s['close']:<6.2f} | +{s['chg_pct']:<10.2f}% | {s['vol_ratio']:<8.2f}x | +{s['prior_3m']:<10.2f}%", flush=True)

    print(f"\n--------------------------------------------------------------------------", flush=True)
    print(f" STEP 3 OUTPUT: EXACT BACKTEST LEADERBOARD SELECTION ({len(step3_candidates)} Candidates)", flush=True)
    print(f"--------------------------------------------------------------------------", flush=True)
    if not step3_candidates:
        print("  No candidates found on this date.", flush=True)
    else:
        print(f"RANK | {'Ticker':<10} | {'Close (Rs)':<10} | {'Prior 3M Leader':<16} | {'Vol Surge':<10} | {'Est ORB Entry':<14} | {'Est LoD Stop':<12}", flush=True)
        print(f"-"*90, flush=True)
        for rank, s in enumerate(step3_candidates[:10], 1):
            star = " *** (BACKTEST #1 CHOICE)" if rank == 1 else (" ** (BACKTEST #2 CHOICE)" if rank == 2 else "")
            print(f"#{rank:<3} | {s['ticker']:<10} | Rs.{s['close']:<7.2f} | +{s['prior_3m']:<14.1f}% | {s['vol_ratio']:<8.2f}x | Rs. {s['orb_entry']:<10.2f} | Rs. {s['lod_stop']:<8.2f}{star}", flush=True)

    print(f"\nScreener run complete for date {target_date}.\n", flush=True)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].strip() != "" and sys.argv[1].strip().upper() != "LATEST":
        user_date = sys.argv[1]
    else:
        user_date = ""
    run_screener(user_date)
