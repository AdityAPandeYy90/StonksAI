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
    "AVALON.NS", "SHADOWFAX.NS", "BEPL.NS", "ACMESOLAR.NS", "NYKAA.NS", "OFSS.NS", "CARTRADE.NS", "MPSLTD.NS"
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

def run_master_feature_screener():
    all_tickers = fetch_nse_universe()
    print(f"\n[1/2] Fetching OHLCV data for {len(all_tickers)} NSE equities...", flush=True)
    
    stock_data_map = {}
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_stock_chart_data, t): t for t in all_tickers}
        for future in as_completed(futures):
            t, clean_data = future.result()
            if clean_data and len(clean_data) > 100:
                stock_data_map[t] = clean_data

    master_list = []

    print(f"[2/2] Calculating 8 Master Breakout Features & Composite MBS Scores...", flush=True)
    for t, data in stock_data_map.items():
        curr = data[-1]
        prev = data[-2]
        
        # 1. Liquidity Gate
        vol_20 = sum(d['volume'] for d in data[-20:]) / 20.0
        if curr['close'] < MIN_PRICE or vol_20 < MIN_VOLUME_AVG:
            continue
            
        # FEATURE 1: Prior 3M Momentum Leaderboard (Qullamaggie / O'Neil)
        prior_3m = (prev['close'] / data[-60]['close'] - 1) * 100.0 if len(data) >= 60 else 0
        prior_1m = (prev['close'] / data[-20]['close'] - 1) * 100.0 if len(data) >= 20 else 0
        if prior_3m < 20.0 and prior_1m < 15.0:
            continue
            
        # FEATURE 2: 5D Base Range Compression (HTF / VCP)
        last5_high = max(d['high'] for d in data[-5:])
        last5_low = min(d['low'] for d in data[-5:])
        base_range_pct = (last5_high - last5_low) / last5_low * 100.0
        if base_range_pct > 12.0:
            continue
            
        # FEATURE 3: Volume Dry-Up (VDU Ratio = Today Vol / 20D Avg Vol) (Qullamaggie / Minervini)
        vdu_ratio = curr['volume'] / max(1, vol_20)
        
        # FEATURE 4: Narrowest Range in 7 Days (NR7 Check) (Stockbee / Crabel)
        ranges_7d = [d['high'] - d['low'] for d in data[-7:]]
        is_nr7 = (ranges_7d[-1] == min(ranges_7d))
        
        # FEATURE 5: Intraday Spread Contraction (% Spread = (High - Low) / Close) (Minervini VCP)
        today_spread_pct = (curr['high'] - curr['low']) / curr['close'] * 100.0
        
        # FEATURE 6: Surfing 10 EMA Proximity (Qullamaggie)
        closes_10d = [d['close'] for d in data[-10:]]
        ema10 = sum(closes_10d) / 10.0
        ema10_dist_pct = abs(curr['close'] - ema10) / ema10 * 100.0
        
        # FEATURE 7: Minervini Stage 2 Trend Template (NEW)
        closes_50d = [d['close'] for d in data[-50:]]
        sma50 = sum(closes_50d) / 50.0
        high_52w = max(d['high'] for d in data)
        low_52w = min(d['low'] for d in data)
        is_stage2 = (curr['close'] >= sma50) and (curr['close'] >= low_52w * 1.25) and (curr['close'] >= high_52w * 0.75)
        
        # FEATURE 8: Stockbee Trend Intensity TI65 Ratio (NEW)
        closes_7d = [d['close'] for d in data[-7:]]
        sma7 = sum(closes_7d) / 7.0
        closes_65d = [d['close'] for d in data[-65:]]
        sma65 = sum(closes_65d) / 65.0
        ti65 = sma7 / sma65 if sma65 > 0 else 1.0
        
        # --- COMPOSITE MASTER BREAKOUT SCORE (MBS: 0 to 100) ---
        vdu_score = max(0, min(30, (1.0 - vdu_ratio) * 30.0))       # Max 30 pts
        nr7_score = 20.0 if is_nr7 else 0.0                          # Max 20 pts
        spread_score = max(0, min(20, (4.0 - today_spread_pct) * 5.0)) # Max 20 pts
        ema_score = max(0, min(15, (2.0 - ema10_dist_pct) * 7.5))    # Max 15 pts
        stage2_score = 10.0 if is_stage2 else 0.0                   # Max 10 pts
        ti65_score = 5.0 if ti65 >= 1.05 else 0.0                   # Max 5 pts
        
        total_mbs = vdu_score + nr7_score + spread_score + ema_score + stage2_score + ti65_score
        
        clean_ticker = t.replace('.NS', '')
        pivot_price = last5_high
        alert_price = pivot_price * 0.995
        
        master_list.append({
            'ticker': clean_ticker,
            'close': curr['close'],
            'mbs_score': total_mbs,
            'vdu_ratio': vdu_ratio,
            'is_nr7': is_nr7,
            'today_spread': today_spread_pct,
            'base_range': base_range_pct,
            'prior_3m': prior_3m,
            'is_stage2': is_stage2,
            'ti65': ti65,
            'alert_price': alert_price,
            'pivot_price': pivot_price,
            'stop_loss': last5_low
        })

    master_list.sort(key=lambda x: x['mbs_score'], reverse=True)

    # Save to CSV
    os.makedirs("d:/stonks/outputs", exist_ok=True)
    csv_path = "d:/stonks/outputs/option_a_master_features_watchlist.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Ticker", "Close_Rs", "MBS_Score_100", "VDU_Ratio", "Is_NR7", "Spread_Pct", "Base_Pct", "Prior_3M_Pct", "Stage2_Template", "TI65_Ratio", "Set_Alert_Price_Rs", "Pivot_Entry_Rs", "Stop_Loss_Rs"])
        for rank, item in enumerate(master_list, 1):
            writer.writerow([rank, item['ticker'], f"{item['close']:.2f}", f"{item['mbs_score']:.1f}", f"{item['vdu_ratio']:.2f}", item['is_nr7'], f"{item['today_spread']:.1f}", f"{item['base_range']:.1f}", f"{item['prior_3m']:.1f}", item['is_stage2'], f"{item['ti65']:.2f}", f"{item['alert_price']:.2f}", f"{item['pivot_price']:.2f}", f"{item['stop_loss']:.2f}"])

    print(f"\n==========================================================================================", flush=True)
    print(f"      OPTION A MASTER BREAKOUT FEATURE SCREENER (8 AUTHORITATIVE FEATURES)                 ", flush=True)
    print(f"==========================================================================================", flush=True)
    print(f" Analyzed {len(master_list)} Option A candidates using 8 Master Quantitative Features!")
    print(f" Full Master Feature CSV exported to: outputs/option_a_master_features_watchlist.csv\n")
    print(f"RANK | {'Ticker':<10} | {'Close (Rs)':<10} | {'MBS Score':<10} | {'Vol Ratio (VDU)':<16} | {'Is NR7?':<8} | {'Spread':<8} | {'Stage 2?':<8} | {'Set Alert At':<14} | {'Pivot Entry':<12}", flush=True)
    print(f"-"*120, flush=True)
    
    for rank, p in enumerate(master_list[:15], 1):
        nr7_str = "YES [NR7]" if p['is_nr7'] else "No"
        stg_str = "YES" if p['is_stage2'] else "No"
        star = " *** (MASTER BREAKOUT LEADER)" if rank <= 3 else ""
        print(f"#{rank:<3} | {p['ticker']:<10} | Rs.{p['close']:<7.2f} | {p['mbs_score']:<9.1f}/100 | {p['vdu_ratio']:<15.2f}x | {nr7_str:<8} | {p['today_spread']:<7.1f}% | {stg_str:<8} | Rs. {p['alert_price']:<10.2f} | Rs. {p['pivot_price']:<10.2f}{star}", flush=True)

    print(f"\nMaster Feature Screener complete.\n", flush=True)

if __name__ == "__main__":
    run_master_feature_screener()
