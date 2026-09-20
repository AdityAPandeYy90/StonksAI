import urllib.request
import json
import csv
import io
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

UNIVERSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 50.0
MIN_VOLUME_AVG = 100000
NUM_THREADS = 50
OUTPUT_DIR = "outputs"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_nse_tickers():
    print("Fetching active EQ ticker list from NSE India...", flush=True)
    try:
        req = urllib.request.Request(UNIVERSE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
        
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        header_lower = [h.strip().lower() for h in header]
        symbol_idx = header_lower.index("symbol")
        series_idx = header_lower.index("series") if "series" in header_lower else -1
        
        tickers = []
        for row in reader:
            if row and len(row) > symbol_idx:
                symbol = row[symbol_idx].strip()
                if series_idx != -1 and len(row) > series_idx:
                    series = row[series_idx].strip().upper()
                    if series != "EQ":
                        continue
                if symbol:
                    tickers.append(f"{symbol}.NS")
        print(f"Loaded {len(tickers)} active EQ tickers from NSE successfully.", flush=True)
        return tickers
    except Exception as e:
        print(f"Error fetching ticker list: {e}", flush=True)
        sys.exit(1)

def fetch_stock_5y_data(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
        
        chart_result = res_data.get('chart', {}).get('result', [])
        if not chart_result:
            return ticker, None
            
        result = chart_result[0]
        timestamps = result.get('timestamp', [])
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        close_prices = quote.get('close', [])
        volume_data = quote.get('volume', [])
        
        clean_data = []
        for t, c, v in zip(timestamps, close_prices, volume_data):
            if t is not None and c is not None and v is not None:
                d_str = datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d')
                clean_data.append({
                    'date': d_str,
                    'close': float(c),
                    'volume': int(v)
                })
        return ticker, clean_data
    except Exception:
        return ticker, None

def evaluate_user_tree(metrics, is_above_10ema):
    t2108 = metrics['t2108']
    dcr5 = metrics['dcr_5']
    pct13 = metrics['pct_13_34d']
    
    tier = "SKIP"
    if t2108 >= 60.0:
        if dcr5 >= 1.8:
            if pct13 >= 28.0:
                tier = "FULL"
            elif pct13 >= 23.0:
                tier = "HALF2"
            else:
                tier = "HALF1"
        else:
            if pct13 >= 28.0:
                tier = "HALF2"
            elif pct13 >= 23.0:
                tier = "HALF1"
            else:
                tier = "SKIP"
    elif 45.0 <= t2108 < 60.0:
        if dcr5 >= 1.2:
            if pct13 >= 20.0:
                tier = "HALF2"
            else:
                tier = "SKIP"
        else:
            tier = "SKIP"
    else:
        tier = "SKIP"
        
    if not is_above_10ema:
        downgrade_map = {"FULL": "HALF2", "HALF2": "HALF1", "HALF1": "SKIP", "SKIP": "SKIP"}
        tier = downgrade_map[tier]
        
    return tier

def evaluate_proposed_tree(metrics, prior_move_pct):
    dcr10 = metrics['dcr_10']
    p25 = metrics['25_1m']
    
    if dcr10 < 1.0 or p25 < 20 or prior_move_pct < 25.0:
        return "SKIP"
    elif dcr10 >= 1.5 and p25 >= 40:
        return "FULL"
    else:
        return "HALF"

def evaluate_hybrid_tree(metrics, is_above_10ema, prior_move_pct):
    t2108 = metrics['t2108']
    dcr10 = metrics['dcr_10']
    p25 = metrics['25_1m']
    
    if t2108 < 45.0 or not is_above_10ema or prior_move_pct < 25.0 or dcr10 < 1.0 or p25 < 20:
        return "SKIP"
    elif dcr10 >= 1.5 and p25 >= 40:
        return "FULL"
    else:
        return "HALF"

def main():
    print("==========================================================================", flush=True)
    print("      5-YEAR MULTI-YEAR DECISION TREE BACKTESTING ENGINE (NSE INDIA)       ", flush=True)
    print("==========================================================================", flush=True)
    
    all_tickers = fetch_nse_tickers()
    
    # Take liquid sample of top 400 tickers for fast, robust 5-year execution
    sample_tickers = all_tickers[:400]
    
    print(f"\nDownloading 5 years of daily chart data for {len(sample_tickers)} liquid symbols using {NUM_THREADS} threads...", flush=True)
    ticker_data_map = {}
    completed = 0
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_stock_5y_data, t): t for t in sample_tickers}
        for future in as_completed(futures):
            t, clean_data = future.result()
            completed += 1
            if completed % 100 == 0 or completed == len(sample_tickers):
                print(f"Downloaded 5y data for {completed}/{len(sample_tickers)} symbols...", flush=True)
            if clean_data and len(clean_data) > 100:
                ticker_data_map[t] = clean_data
                
    print(f"\nLoaded valid 5-year data for {len(ticker_data_map)} liquid NSE stocks.", flush=True)
    
    all_dates_set = set()
    for t, data in ticker_data_map.items():
        for item in data:
            all_dates_set.add(item['date'])
            
    sorted_dates = sorted(list(all_dates_set))
    total_days = len(sorted_dates)
    print(f"Total historical trading days in 5-year window: {total_days}", flush=True)
    
    date_to_idx = {d: i for i, d in enumerate(sorted_dates)}
    
    ticker_history = {}
    for t, data in ticker_data_map.items():
        hist = {}
        for item in data:
            d = item['date']
            hist[date_to_idx[d]] = item
        ticker_history[t] = hist
        
    print("\nComputing 5-Year daily exchange market breadth metrics...", flush=True)
    daily_metrics = {}
    
    for idx in range(40, total_days):
        date_str = sorted_dates[idx]
        
        count_4_plus = 0
        count_4_minus = 0
        count_13_plus = 0
        count_25_plus_1m = 0
        total_eligible = 0
        stocks_above_40sma = 0
        
        for t, hist in ticker_history.items():
            if idx not in hist or (idx - 1) not in hist:
                continue
            curr = hist[idx]
            prev = hist[idx - 1]
            
            vol_sum = 0
            vol_count = 0
            for v_idx in range(max(0, idx - 19), idx + 1):
                if v_idx in hist:
                    vol_sum += hist[v_idx]['volume']
                    vol_count += 1
            avg_vol = vol_sum / vol_count if vol_count > 0 else 0
            
            if curr['close'] < MIN_PRICE or avg_vol < MIN_VOLUME_AVG:
                continue
                
            total_eligible += 1
            
            sma40_sum = 0
            sma40_cnt = 0
            for s_idx in range(max(0, idx - 39), idx + 1):
                if s_idx in hist:
                    sma40_sum += hist[s_idx]['close']
                    sma40_cnt += 1
            sma40 = sma40_sum / sma40_cnt if sma40_cnt > 0 else 0
            if curr['close'] > sma40:
                stocks_above_40sma += 1
                
            chg1d = curr['close'] / prev['close']
            if chg1d >= 1.04:
                count_4_plus += 1
            elif chg1d <= 0.96:
                count_4_minus += 1
                
            if (idx - 34) in hist and (curr['close'] / hist[idx - 34]['close']) >= 1.13:
                count_13_plus += 1
                
            if (idx - 21) in hist and (curr['close'] / hist[idx - 21]['close']) >= 1.25:
                count_25_plus_1m += 1
                
        daily_metrics[date_str] = {
            'idx': idx,
            'eligible': total_eligible,
            '4_plus': count_4_plus,
            '4_minus': count_4_minus,
            '13_plus': count_13_plus,
            'pct_13_34d': (count_13_plus / total_eligible * 100) if total_eligible > 0 else 0,
            '25_1m': count_25_plus_1m,
            't2108': (stocks_above_40sma / total_eligible * 100) if total_eligible > 0 else 0
        }
        
    for date_str, m in daily_metrics.items():
        idx = m['idx']
        sum5_plus = sum(daily_metrics[sorted_dates[i]]['4_plus'] for i in range(max(40, idx - 4), idx + 1) if sorted_dates[i] in daily_metrics)
        sum5_minus = sum(daily_metrics[sorted_dates[i]]['4_minus'] for i in range(max(40, idx - 4), idx + 1) if sorted_dates[i] in daily_metrics)
        sum10_plus = sum(daily_metrics[sorted_dates[i]]['4_plus'] for i in range(max(40, idx - 9), idx + 1) if sorted_dates[i] in daily_metrics)
        sum10_minus = sum(daily_metrics[sorted_dates[i]]['4_minus'] for i in range(max(40, idx - 9), idx + 1) if sorted_dates[i] in daily_metrics)
        
        m['dcr_5'] = (sum5_plus / sum5_minus) if sum5_minus > 0 else sum5_plus
        m['dcr_10'] = (sum10_plus / sum10_minus) if sum10_minus > 0 else sum10_plus

    breadth_file = os.path.join(OUTPUT_DIR, "multi_year_5y_daily_breadth.csv")
    print(f"\nWriting 5-year daily market breadth history to separate file: {breadth_file}...", flush=True)
    with open(breadth_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "EligibleUniverse", "4%Plus", "4%Minus", "5D_DCR", "10D_DCR", "25%Plus1M", "Pct13_34d", "T2108"])
        for d in sorted_dates[40:]:
            if d in daily_metrics:
                m = daily_metrics[d]
                writer.writerow([d, m['eligible'], m['4_plus'], m['4_minus'], f"{m['dcr_5']:.2f}", f"{m['dcr_10']:.2f}", m['25_1m'], f"{m['pct_13_34d']:.2f}", f"{m['t2108']:.2f}"])

    print("\nRunning 5-Year Decision Tree Backtest for all 3 Strategy Trees...", flush=True)
    user_trades = []
    proposed_trades = []
    hybrid_trades = []

    for t, hist in ticker_history.items():
        indices = sorted(hist.keys())
        closes = [hist[i]['close'] for i in indices]
        
        ema10_map = {}
        if closes:
            k = 2 / 11
            ema = closes[0]
            for i, c in zip(indices, closes):
                ema = c * k + ema * (1 - k)
                ema10_map[i] = ema

        for idx in indices:
            if idx < 40 or (idx + 5) not in hist or (idx - 1) not in hist:
                continue
                
            curr = hist[idx]
            prev = hist[idx - 1]
            date_str = curr['date']
            
            if curr['close'] < MIN_PRICE:
                continue
                
            chg1d = (curr['close'] / prev['close'] - 1) * 100
            
            if chg1d >= 4.0 and date_str in daily_metrics:
                m = daily_metrics[date_str]
                is_above_10ema = curr['close'] > ema10_map.get(idx, 0)
                
                past_prices = [hist[s]['close'] for s in range(max(0, idx - 40), idx) if s in hist]
                min_p = min(past_prices) if past_prices else prev['close']
                prior_move_pct = (prev['close'] / min_p - 1) * 100
                
                ret_5d = (hist[idx + 5]['close'] / curr['close'] - 1) * 100
                ret_10d = (hist[idx + 10]['close'] / curr['close'] - 1) * 100 if (idx + 10) in hist else ret_5d
                
                u_signal = evaluate_user_tree(m, is_above_10ema)
                if u_signal != "SKIP":
                    user_trades.append({'date': date_str, 'ticker': t, 'signal': u_signal, 'ret_5d': ret_5d, 'ret_10d': ret_10d})
                    
                p_signal = evaluate_proposed_tree(m, prior_move_pct)
                if p_signal != "SKIP":
                    proposed_trades.append({'date': date_str, 'ticker': t, 'signal': p_signal, 'ret_5d': ret_5d, 'ret_10d': ret_10d})
                    
                h_signal = evaluate_hybrid_tree(m, is_above_10ema, prior_move_pct)
                if h_signal != "SKIP":
                    hybrid_trades.append({'date': date_str, 'ticker': t, 'signal': h_signal, 'ret_5d': ret_5d, 'ret_10d': ret_10d})

    trades_file = os.path.join(OUTPUT_DIR, "multi_year_5y_backtest_trades.csv")
    print(f"Writing all backtest trade logs to separate file: {trades_file}...", flush=True)
    with open(trades_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Ticker", "StrategyTree", "SignalTier", "5D_Return_Pct", "10D_Return_Pct", "Win_Status"])
        for tr in user_trades:
            writer.writerow([tr['date'], tr['ticker'].replace('.NS',''), "UserHandwrittenTree", tr['signal'], f"{tr['ret_5d']:.2f}", f"{tr['ret_10d']:.2f}", "WIN" if tr['ret_5d'] > 0 else "LOSS"])
        for tr in proposed_trades:
            writer.writerow([tr['date'], tr['ticker'].replace('.NS',''), "ProposedTree", tr['signal'], f"{tr['ret_5d']:.2f}", f"{tr['ret_10d']:.2f}", "WIN" if tr['ret_5d'] > 0 else "LOSS"])
        for tr in hybrid_trades:
            writer.writerow([tr['date'], tr['ticker'].replace('.NS',''), "HybridMasterTree", tr['signal'], f"{tr['ret_5d']:.2f}", f"{tr['ret_10d']:.2f}", "WIN" if tr['ret_5d'] > 0 else "LOSS"])

    print("\n==========================================================================", flush=True)
    print("       5-YEAR MULTI-YEAR BACKTESTING RESULTS SUMMARY (NSE INDIA)         ", flush=True)
    print("==========================================================================", flush=True)
    
    def calc_stats(trades_list, name):
        if not trades_list:
            print(f"{name}: No trades generated.", flush=True)
            return
        total = len(trades_list)
        wins = sum(1 for tr in trades_list if tr['ret_5d'] > 0)
        win_rate = (wins / total) * 100
        avg_5d = sum(tr['ret_5d'] for tr in trades_list) / total
        avg_10d = sum(tr['ret_10d'] for tr in trades_list) / total
        win_avg = sum(tr['ret_5d'] for tr in trades_list if tr['ret_5d'] > 0) / wins if wins > 0 else 0
        loss_cnt = total - wins
        loss_avg = sum(tr['ret_5d'] for tr in trades_list if tr['ret_5d'] <= 0) / loss_cnt if loss_cnt > 0 else 0
        profit_factor = abs(sum(tr['ret_5d'] for tr in trades_list if tr['ret_5d'] > 0) / sum(tr['ret_5d'] for tr in trades_list if tr['ret_5d'] <= 0)) if loss_cnt > 0 and sum(tr['ret_5d'] for tr in trades_list if tr['ret_5d'] <= 0) != 0 else 999.0
        
        print(f"\n--- {name} ---", flush=True)
        print(f"  Total Trades Allowed   : {total}", flush=True)
        print(f"  5-Day Win Rate (%)     : {win_rate:.2f}% ({wins} Wins / {loss_cnt} Losses)", flush=True)
        print(f"  Average 5-Day Return   : {avg_5d:+.2f}%", flush=True)
        print(f"  Average 10-Day Return  : {avg_10d:+.2f}%", flush=True)
        print(f"  Avg Winner Return      : {win_avg:+.2f}%", flush=True)
        print(f"  Avg Loser Return       : {loss_avg:+.2f}%", flush=True)
        print(f"  Profit Factor (5D)     : {profit_factor:.2f}", flush=True)

    calc_stats(user_trades, "1. USER'S HANDWRITTEN DECISION TREE")
    calc_stats(proposed_trades, "2. PREVIOUSLY PROPOSED DECISION TREE")
    calc_stats(hybrid_trades, "3. HYBRID MASTER DECISION TREE (BEST OF BOTH)")

    summary_md = os.path.join(OUTPUT_DIR, "multi_year_5y_backtest_report.md")
    print(f"\nWriting summary markdown report to separate file: {summary_md}...", flush=True)
    with open(summary_md, 'w', encoding='utf-8') as f:
        f.write("# 5-Year Multi-Year Decision Tree Backtest Report (NSE India)\n\n")
        f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"- Total NSE Liquid Tickers Evaluated: {len(ticker_data_map)}\n")
        f.write(f"- Total Historical Trading Days: {total_days}\n\n")
        f.write("## Strategy Performance Comparison\n\n")
        f.write("| Strategy Tree | Total Trades | 5D Win Rate (%) | Avg 5D Return | Avg 10D Return |\n")
        f.write("|---|---|---|---|---|\n")
        
        for name, t_list in [("User Handwritten Tree", user_trades), ("Proposed Tree", proposed_trades), ("Hybrid Master Tree", hybrid_trades)]:
            if t_list:
                tot = len(t_list)
                w = (sum(1 for tr in t_list if tr['ret_5d'] > 0) / tot) * 100
                a5 = sum(tr['ret_5d'] for tr in t_list) / tot
                a10 = sum(tr['ret_10d'] for tr in t_list) / tot
                f.write(f"| {name} | {tot} | {w:.2f}% | {a5:+.2f}% | {a10:+.2f}% |\n")
                
    print("\nBacktest complete! All separate files generated in outputs/ directory.", flush=True)

if __name__ == "__main__":
    main()
