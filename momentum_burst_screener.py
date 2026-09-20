import urllib.request
import json
import csv
import io
import datetime
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# Configurations
UNIVERSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 50.0
MIN_VOLUME_AVG = 100000
NUM_THREADS = 40  # High thread count for fast downloads

def fetch_nse_tickers():
    print("Fetching entire NSE listed stock list...")
    try:
        req = urllib.request.Request(UNIVERSE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
        
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        header = [h.strip() for h in header]
        
        symbol_idx = header.index("SYMBOL")
        series_idx = header.index("SERIES")
        
        tickers = []
        for row in reader:
            if row and len(row) > max(symbol_idx, series_idx):
                symbol = row[symbol_idx].strip()
                series = row[series_idx].strip()
                if symbol and series == "EQ":
                    tickers.append(f"{symbol}.NS")
        print(f"Loaded {len(tickers)} liquid NSE common stocks successfully.")
        return tickers
    except Exception as e:
        print(f"Error fetching ticker list: {e}")
        sys.exit(1)

def fetch_stock_data(ticker):
    # Fetch 1 year of data to calculate 200 SMA trend, 60-day highs, and 2LYNCH parameters
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
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
        open_prices = quote.get('open', [])
        high_prices = quote.get('high', [])
        low_prices = quote.get('low', [])
        volumes = quote.get('volume', [])
        
        meta = result.get('meta', {})
        
        # Patch the final element if it is None (Yahoo Finance EOD delay fix)
        if close_prices and close_prices[-1] is None:
            reg_price = meta.get('regularMarketPrice')
            if reg_price is not None:
                close_prices[-1] = reg_price
                
        if volumes and volumes[-1] is None:
            reg_vol = meta.get('regularMarketVolume')
            if reg_vol is not None:
                volumes[-1] = reg_vol
                
        if open_prices and open_prices[-1] is None:
            open_prices[-1] = close_prices[-1]
        if high_prices and high_prices[-1] is None:
            high_prices[-1] = close_prices[-1]
        if low_prices and low_prices[-1] is None:
            low_prices[-1] = close_prices[-1]
        
        clean_data = []
        for t, o, h, l, c, v in zip(timestamps, open_prices, high_prices, low_prices, close_prices, volumes):
            if all(x is not None for x in [t, o, h, l, c, v]):
                clean_data.append({
                    'date': datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d'),
                    'open': float(o),
                    'high': float(h),
                    'low': float(l),
                    'close': float(c),
                    'volume': int(v)
                })
        return ticker, clean_data
    except Exception:
        return ticker, None

def analyze_candidates(ticker_data_map):
    print("\nAnalyzing stocks using Pradeep Bonde's Momentum Burst philosophy...")
    
    bullish_4pct_list = []
    bearish_4pct_list = []
    bullish_dollar_list = []
    bearish_dollar_list = []
    
    for ticker, data in ticker_data_map.items():
        if not data or len(data) < 200:
            continue
            
        curr = data[-1]
        prev = data[-2]
        prev_2 = data[-3]
        
        close = curr['close']
        prev_close = prev['close']
        open_p = curr['open']
        high = curr['high']
        low = curr['low']
        volume = curr['volume']
        prev_volume = prev['volume']
        
        if close < MIN_PRICE or volume < MIN_VOLUME_AVG:
            continue
            
        pct_change = (close / prev_close - 1) * 100
        co_diff = close - open_p
        pct_co = (co_diff / open_p) * 100
        
        # 1. 200-day Simple Moving Average (SMA) for long-term trend
        closes_200 = [d['close'] for d in data[-200:]]
        sma_200_curr = sum(closes_200) / 200
        closes_200_prev = [d['close'] for d in data[-210:-10]]
        sma_200_prev = sum(closes_200_prev) / 200 if len(closes_200_prev) == 200 else sma_200_curr
        
        is_uptrend_200 = close > sma_200_curr and sma_200_curr >= sma_200_prev
        is_downtrend_200 = close < sma_200_curr and sma_200_curr <= sma_200_prev
        
        # 2. 2LYNCH checklist calculations
        prev_ret = (prev['close'] / prev_2['close'] - 1) * 100
        if len(data) >= 4:
            prev2_ret = (prev_2['close'] / data[-4]['close'] - 1) * 100
        else:
            prev2_ret = 0
        rule_2_pass = not (prev_ret >= 1.0 and prev2_ret >= 1.0)
        
        # 'L' - Linearity
        n = 40
        closes_40 = [d['close'] for d in data[-n-1:-1]]
        x = list(range(n))
        mean_x = sum(x) / n
        mean_y = sum(closes_40) / n
        num = sum((x[i] - mean_x) * (closes_40[i] - mean_y) for i in range(n))
        den_x = sum((x[i] - mean_x)**2 for i in range(n))
        den_y = sum((closes_40[i] - mean_y)**2 for i in range(n))
        r = num / math.sqrt(den_x * den_y) if (den_x * den_y) > 0 else 0
        rule_L_pass = r >= 0.70  
        
        # 'Y' - Young trend
        past_breakouts = 0
        for i in range(len(data) - 61, len(data) - 1):
            if i <= 0: continue
            ret = (data[i]['close'] / data[i-1]['close'] - 1) * 100
            vol_inc = data[i]['volume'] > data[i-1]['volume']
            if ret >= 4.0 and vol_inc:
                past_breakouts += 1
        rule_Y_pass = past_breakouts <= 2
        
        # 'N' - Narrow range or negative day squeeze
        prev_range = (prev['high'] - prev['low']) / prev['close'] * 100
        ranges = [(d['high'] - d['low']) / d['close'] * 100 for d in data[-7:-2]]  
        avg_range_5d = sum(ranges) / len(ranges) if ranges else 0
        is_nrd = prev_range < avg_range_5d * 0.90
        is_neg_day = prev['close'] < prev_2['close']
        rule_N_pass = is_nrd or is_neg_day
        
        # 'C' - Consolidation quality
        closes_60 = [d['close'] for d in data[-60:]]
        high_60 = max(closes_60)
        drawdown_from_high = (high_60 - close) / high_60 * 100
        is_shallow = drawdown_from_high <= 12.0  
        
        breakdown_count = 0
        for d_idx in range(max(0, len(data) - 11), len(data) - 1):
            day_ret = (data[d_idx]['close'] / data[d_idx-1]['close'] - 1) * 100
            if day_ret <= -4.0:
                breakdown_count += 1
        rule_C_pass = is_shallow and (breakdown_count <= 1)
        
        # 'H' - Close near High
        daily_range = high - low
        close_location = (close - low) / daily_range if daily_range > 0 else 0.5
        rule_H_pass = close_location >= 0.85
        
        # Consolidation highs/lows for triggers
        consol_high = max(d['high'] for d in data[-6:-1]) if len(data) >= 7 else high
        consol_low = min(d['low'] for d in data[-6:-1]) if len(data) >= 7 else low
        
        stock_info = {
            'ticker': ticker.replace('.NS', ''),
            'close': close,
            'open': open_p,
            'high': high,
            'low': low,
            'pct_change': pct_change,
            'co_diff': co_diff,
            'pct_co': pct_co,
            'volume': volume,
            'close_location': close_location,
            'rule_2_pass': rule_2_pass,
            'rule_L_pass': rule_L_pass,
            'rule_Y_pass': rule_Y_pass,
            'rule_N_pass': rule_N_pass,
            'rule_C_pass': rule_C_pass,
            'rule_H_pass': rule_H_pass,
            'consol_high': consol_high,
            'consol_low': consol_low,
            'is_uptrend_200': is_uptrend_200,
            'is_downtrend_200': is_downtrend_200,
            'drawdown_from_high': drawdown_from_high
        }
        
        # 1. 4% Bullish Breakout
        if pct_change >= 4.0 and volume > prev_volume and close > open_p:
            bullish_4pct_list.append(stock_info)
            
        # 2. 4% Bearish Breakdown
        if pct_change <= -4.0 and volume > prev_volume and close < open_p:
            bearish_4pct_list.append(stock_info)
            
        # 3. Bullish Dollar Breakout
        if co_diff >= 10.0 and close > open_p:
            if not (pct_change >= 4.0 and volume > prev_volume):
                bullish_dollar_list.append(stock_info)
                
        # 4. Bearish Dollar Breakdown
        if co_diff <= -10.0 and close < open_p:
            if not (pct_change <= -4.0 and volume > prev_volume):
                bearish_dollar_list.append(stock_info)

    bullish_4pct_list.sort(key=lambda x: x['co_diff'], reverse=True)
    bullish_dollar_list.sort(key=lambda x: x['co_diff'], reverse=True)
    bearish_4pct_list.sort(key=lambda x: x['co_diff'])
    bearish_dollar_list.sort(key=lambda x: x['co_diff'])
    
    return bullish_4pct_list, bearish_4pct_list, bullish_dollar_list, bearish_dollar_list

def evaluate_candidate(c, is_bearish=False):
    """
    Evaluates a candidate and returns its classification:
    - 'CLASSIC': Passes rising 200 SMA and all 2LYNCH checks.
    - 'BOTTOM_BOUNCE': Is below 200 SMA or has deep drawdown, but shows massive range expansion and passes 2 and N.
    - 'SKIP': Does not fit either high-probability category.
    """
    if is_bearish:
        if c['is_downtrend_200'] and c['close_location'] <= 0.15:
            return "SHORT CANDIDATE"
        return "SKIP"

    # 1. Check for Classic 2LYNCH Breakout
    classic_failures = []
    if not c['is_uptrend_200']:
        classic_failures.append("NOT_UPTREND")
    if not c['rule_2_pass']:
        classic_failures.append("2 (Up 2 Days)")
    if not c['rule_L_pass']:
        classic_failures.append("L (Not Linear)")
    if not c['rule_Y_pass']:
        classic_failures.append("Y (Old Trend)")
    if not c['rule_N_pass']:
        classic_failures.append("N (No Squeeze)")
    if not c['rule_C_pass']:
        classic_failures.append("C (Bad Consol)")
    if not c['rule_H_pass']:
        classic_failures.append("H (Faded)")
        
    if not classic_failures:
        return "CLASSIC BUY"
        
    # 2. Check for Bottom Bounce / Reversal
    # Bottom Bounce rules:
    # - Doesn't need 200 SMA uptrend.
    # - Must show strong daily range expansion: up >= 5% OR C-O >= Rs 15
    # - Must close near high (H pass: location >= 0.85)
    # - Must pass 2 (Not up 2 days before today) and N (Narrow range/negative day squeeze yesterday)
    is_strong_bounce = (c['pct_change'] >= 5.0) or (c['co_diff'] >= 15.0)
    if is_strong_bounce and c['rule_2_pass'] and c['rule_N_pass'] and c['rule_H_pass']:
        return "BOTTOM BOUNCE"
        
    # Build skip reason based on Classic failures
    return f"SKIP ({', '.join(classic_failures)})"

def print_table(title, candidates, is_bearish=False):
    print("\n" + "="*115)
    print(f" {title} ({len(candidates)} candidates) - Sorted by (Close - Open) ")
    print("="*115)
    if not is_bearish:
        print(f"{'Ticker':10} | {'Close':8} | {'% Chg':6} | {'C-O (Rs)':8} | {'2':1} | {'L':1} | {'Y':1} | {'N':1} | {'C':1} | {'H':1} | {'Action'}")
        print("-"*115)
        for c in candidates[:25]:
            action = evaluate_candidate(c, is_bearish=False)
            c2 = "P" if c['rule_2_pass'] else "F"
            cL = "P" if c['rule_L_pass'] else "F"
            cY = "P" if c['rule_Y_pass'] else "F"
            cN = "P" if c['rule_N_pass'] else "F"
            cC = "P" if c['rule_C_pass'] else "F"
            cH = "P" if c['rule_H_pass'] else "F"
            print(f"{c['ticker']:10} | {c['close']:8.2f} | {c['pct_change']:+5.1f}% | {c['co_diff']:+8.2f} | {c2:1} | {cL:1} | {cY:1} | {cN:1} | {cC:1} | {cH:1} | {action}")
    else:
        print(f"{'Ticker':10} | {'Close':8} | {'% Chg':6} | {'C-O (Rs)':8} | {'Cls% Range':10} | {'Action'}")
        print("-"*115)
        for c in candidates[:25]:
            action = evaluate_candidate(c, is_bearish=True)
            close_range_pct = c['close_location'] * 100
            print(f"{c['ticker']:10} | {c['close']:8.2f} | {c['pct_change']:+5.1f}% | {c['co_diff']:+8.2f} | {close_range_pct:8.1f}% | {action}")
            
    if len(candidates) > 25:
        print(f"...and {len(candidates) - 25} more candidates.")
    print("="*115)

def print_executable_watchlist(bullish_list, bearish_list):
    print("\n" + "#"*115)
    print("        FINAL ACTIONABLE EXECUTE WATCHLIST FOR TOMORROW (2LYNCH & BOTTOM BOUNCE QUALIFIED)        ")
    print("#"*115)
    
    print("\n[BULLISH EXECUTES - CLASSIC 2LYNCH BREAKOUTS]")
    print(f"{'Ticker':10} | {'Close':8} | {'% Chg':6} | {'C-O (Rs)':8} | {'ConsolHigh':10} | {'Suggested Trigger (Today High)'}")
    print("-"*115)
    classic_count = 0
    for c in bullish_list:
        action = evaluate_candidate(c, is_bearish=False)
        if action == "CLASSIC BUY":
            print(f"{c['ticker']:10} | {c['close']:8.2f} | {c['pct_change']:+5.1f}% | {c['co_diff']:+8.2f} | {c['consol_high']:10.2f} | Buy Alert at Rs.{c['high']:.2f}")
            classic_count += 1
    if classic_count == 0:
        print("No classic 2LYNCH platform breakouts qualified today.")
        
    print("\n[BULLISH EXECUTES - EXPLOSIVE BOTTOM BOUNCES]")
    print(f"{'Ticker':10} | {'Close':8} | {'% Chg':6} | {'C-O (Rs)':8} | {'ConsolHigh':10} | {'Suggested Trigger (Today High)'}")
    print("-"*115)
    bounce_count = 0
    for c in bullish_list:
        action = evaluate_candidate(c, is_bearish=False)
        if action == "BOTTOM BOUNCE":
            print(f"{c['ticker']:10} | {c['close']:8.2f} | {c['pct_change']:+5.1f}% | {c['co_diff']:+8.2f} | {c['consol_high']:10.2f} | Buy Alert at Rs.{c['high']:.2f}")
            bounce_count += 1
    if bounce_count == 0:
        print("No explosive bottom bounces qualified today.")
        
    print("\n[BEARISH EXECUTES (SHORT)] - Sell as it breaks today's low:")
    print(f"{'Ticker':10} | {'Close':8} | {'% Chg':6} | {'C-O (Rs)':8} | {'ConsolLow':10} | {'Suggested Trigger (Today Low)'}")
    print("-"*115)
    short_count = 0
    for c in bearish_list:
        action = evaluate_candidate(c, is_bearish=True)
        if action == "SHORT CANDIDATE":
            print(f"{c['ticker']:10} | {c['close']:8.2f} | {c['pct_change']:+5.1f}% | {c['co_diff']:+8.2f} | {c['consol_low']:10.2f} | Short Alert at Rs.{c['low']:.2f}")
            short_count += 1
    if short_count == 0:
        print("No high-probability short setups found today.")
    print("#"*115 + "\n")

def main():
    tickers = fetch_nse_tickers()
    print(f"Downloading data for {len(tickers)} tickers...")
    
    ticker_data_map = {}
    completed_count = 0
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_stock_data, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                t, clean_data = future.result()
                ticker_data_map[t] = clean_data
            except Exception:
                ticker_data_map[ticker] = None
            completed_count += 1
            if completed_count % 100 == 0:
                print(f"Downloaded {completed_count}/{len(tickers)} symbols...")
                
    bullish_4pct, bearish_4pct, bullish_dollar, bearish_dollar = analyze_candidates(ticker_data_map)
    
    # Run the raw print tables
    print_table("1. BULLISH 4% MOMENTUM BURST BREAKOUTS", bullish_4pct)
    print_table("2. BULLISH INR 10+ DOLLAR BREAKOUTS", bullish_dollar)
    print_table("3. BEARISH 4% MOMENTUM BURST BREAKDOWNS", bearish_4pct, is_bearish=True)
    print_table("4. BEARISH INR 10+ DOLLAR BREAKDOWNS", bearish_dollar, is_bearish=True)
    
    # Combined lists for the final watchlist
    all_bullish = bullish_4pct + bullish_dollar
    all_bearish = bearish_4pct + bearish_dollar
    
    # Print the curated final watchlist
    print_executable_watchlist(all_bullish, all_bearish)

if __name__ == "__main__":
    main()
