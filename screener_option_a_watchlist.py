import urllib.request
import json
import csv
import io
import datetime
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

UNIVERSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 50.0
MIN_VOLUME_AVG = 100000
NUM_THREADS = 50

FALLBACK_TICKERS = [
    "AURIONPRO.NS", "CLSEL.NS", "BEML.NS", "HAL.NS", "MAZDOCK.NS", "BALUFORGE.NS", 
    "BBOX.NS", "AEGISLOG.NS", "CEMPRO.NS", "BHAGYANGR.NS", "BETA.NS", "ASHOKA.NS",
    "BAJAJCON.NS", "BSOFT.NS", "CHOLAFIN.NS", "CHOLAHLDNG.NS", "BANSWRAS.NS", "ABB.NS",
    "TATAELXSI.NS", "POLYCAB.NS", "PERSISTENT.NS", "DIXON.NS", "KAYNES.NS", "DATAPATTNS.NS",
    "AVALON.NS", "SHADOWFAX.NS", "SETL.NS", "SIGMAADV.NS", "DIACABS.NS", "SANGINITA.NS", "FILATEX.NS"
]

def fetch_nse_universe():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib.request.Request(UNIVERSE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
            content = response.read().decode('utf-8')
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        symbol_idx = [h.strip().lower() for h in header].index("symbol")
        tickers = [row[symbol_idx].strip() + ".NS" for row in reader if row and len(row) > symbol_idx]
        if len(tickers) > 500:
            return tickers
    except Exception:
        pass
    return FALLBACK_TICKERS

def fetch_stock_chart_data(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
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

def run_option_a_screener():
    all_tickers = fetch_nse_universe()
    print(f"\n[1/2] Scanning {len(all_tickers)} NSE equities for Option A High Tight Flag Watchlist...", flush=True)
    
    stock_data_map = {}
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_stock_chart_data, t): t for t in all_tickers}
        for future in as_completed(futures):
            t, clean_data = future.result()
            if clean_data and len(clean_data) > 60:
                stock_data_map[t] = clean_data

    watchlist = []

    for t, data in stock_data_map.items():
        curr = data[-1]
        prev = data[-2]
        
        # 1. Liquidity Check
        vol_20 = sum(d['volume'] for d in data[-20:]) / 20.0
        if curr['close'] < MIN_PRICE or vol_20 < MIN_VOLUME_AVG:
            continue
            
        # 2. Prior Momentum Check (3-Month & 1-Month Leaders)
        prior_3m_move = (prev['close'] / data[-60]['close'] - 1) * 100.0 if len(data) >= 60 else 0
        prior_1m_move = (prev['close'] / data[-20]['close'] - 1) * 100.0 if len(data) >= 20 else 0
        
        if prior_3m_move < 25.0 and prior_1m_move < 15.0:
            continue
            
        # 3. Tight Consolidation Base Check (High Tight Flag Range over last 5 days)
        last5_high = max(d['high'] for d in data[-5:])
        last5_low = min(d['low'] for d in data[-5:])
        base_range_pct = (last5_high - last5_low) / last5_low * 100.0
        
        if base_range_pct > 12.0:
            continue
            
        composite_score = (prior_3m_move * 0.7) + (prior_1m_move * 0.3)
        clean_ticker = t.replace('.NS', '')
        pivot_price = last5_high
        alert_price = pivot_price * 0.995
        
        watchlist.append({
            'ticker': clean_ticker,
            'close': curr['close'],
            'prior_3m': prior_3m_move,
            'prior_1m': prior_1m_move,
            'composite_score': composite_score,
            'base_range': base_range_pct,
            'pivot_price': pivot_price,
            'alert_price': alert_price,
            'stop_loss': last5_low
        })

    watchlist.sort(key=lambda x: x['composite_score'], reverse=True)

    # Save full watchlist to CSV
    os.makedirs("d:/stonks/outputs", exist_ok=True)
    csv_path = "d:/stonks/outputs/option_a_full_watchlist.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Ticker", "Close_Rs", "Prior_3M_Pct", "Base_Range_Pct", "Set_Alert_Price_Rs", "Pivot_Entry_Rs", "Stop_Loss_Rs"])
        for rank, w in enumerate(watchlist, 1):
            writer.writerow([rank, w['ticker'], f"{w['close']:.2f}", f"{w['prior_3m']:.1f}", f"{w['base_range']:.1f}", f"{w['alert_price']:.2f}", f"{w['pivot_price']:.2f}", f"{w['stop_loss']:.2f}"])

    print(f"\n==========================================================================", flush=True)
    print(f"    OPTION A NIGHTLY WATCHLIST: TIGHT BASE BREAKOUT CANDIDATES (DAY 0)   ", flush=True)
    print(f"==========================================================================", flush=True)
    print(f" Found {len(watchlist)} stocks coiling in tight bases across full exchange!")
    print(f" Full watchlist exported to: outputs/option_a_full_watchlist.csv\n")
    print(f"RANK | {'Ticker':<10} | {'Close (Rs)':<10} | {'Prior 3M':<10} | {'5D Base Range':<12} | {'Set Mobile Alert At':<20} | {'Pivot Entry':<12} | {'Stop Loss':<10}", flush=True)
    print(f"-"*110, flush=True)
    
    for rank, w in enumerate(watchlist[:15], 1):
        star = " *** (TOP DAY 0 CHOICE)" if rank <= 3 else ""
        print(f"#{rank:<3} | {w['ticker']:<10} | Rs.{w['close']:<7.2f} | +{w['prior_3m']:<8.1f}% | {w['base_range']:<10.1f}% | Rs. {w['alert_price']:<16.2f} | Rs. {w['pivot_price']:<10.2f} | Rs. {w['stop_loss']:<8.2f}{star}", flush=True)

    print(f"\nOption A Watchlist screener complete.\n", flush=True)

if __name__ == "__main__":
    run_option_a_screener()
