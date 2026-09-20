import urllib.request
import json
import csv
import io
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# Configurations
UNIVERSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 50.0
MIN_VOLUME_AVG = 100000
NUM_THREADS = 40

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
    # Fetch 15 days of data for the 5-day post-mortem check
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"
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
        
        # Patch EOD delay if necessary
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
                    'close': float(c),
                    'volume': int(v)
                })
        return ticker, clean_data
    except Exception:
        return ticker, None

def analyze_post_mortem(ticker_data_map):
    print("\nRunning post-mortem analysis for stocks up 20%+ in the last 5 days...")
    
    bullish_movers = []
    bearish_movers = []
    
    for ticker, data in ticker_data_map.items():
        if not data or len(data) < 6:
            continue
            
        # Get last 5 days
        curr_close = data[-1]['close']
        prev_5_close = data[-6]['close']  # 5 days ago close
        
        if curr_close < MIN_PRICE:
            continue
            
        # Liquidity check: volume in each of the last 3 days >= 100k
        liquidity_ok = True
        for d in data[-3:]:
            if d['volume'] < MIN_VOLUME_AVG:
                liquidity_ok = False
                break
                
        if not liquidity_ok:
            continue
            
        gain_pct = (curr_close / prev_5_close - 1) * 100
        
        stock_info = {
            'ticker': ticker.replace('.NS', ''),
            'close': curr_close,
            'gain_pct': gain_pct
        }
        
        if gain_pct >= 20.0:
            bullish_movers.append(stock_info)
        elif gain_pct <= -20.0:
            bearish_movers.append(stock_info)
            
    bullish_movers.sort(key=lambda x: x['gain_pct'], reverse=True)
    bearish_movers.sort(key=lambda x: x['gain_pct'])
    
    return bullish_movers, bearish_movers

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
                
    bullish, bearish = analyze_post_mortem(ticker_data_map)
    
    print("\n" + "#"*80)
    print("      POST-MORTEM ANALYSIS: STOCKS UP 20%+ IN THE LAST 5 TRADING DAYS      ")
    print("       (Use this list to study daily & train your visual memory!)        ")
    print("#"*80)
    print(f"{'Ticker':12} | {'Close (Rs)':12} | {'5-Day Gain %':15}")
    print("-"*80)
    for s in bullish:
        print(f"{s['ticker']:12} | {s['close']:12.2f} | {s['gain_pct']:+.2f}%")
    if not bullish:
        print("No stocks gained 20%+ in the last 5 days.")
    print("#"*80 + "\n")
    
    print("\n" + "#"*80)
    print("     POST-MORTEM ANALYSIS: STOCKS DOWN 20%+ IN THE LAST 5 TRADING DAYS      ")
    print("#"*80)
    print(f"{'Ticker':12} | {'Close (Rs)':12} | {'5-Day Loss %':15}")
    print("-"*80)
    for s in bearish:
        print(f"{s['ticker']:12} | {s['close']:12.2f} | {s['gain_pct']:+.2f}%")
    if not bearish:
        print("No stocks lost 20%+ in the last 5 days.")
    print("#"*80 + "\n")

if __name__ == "__main__":
    main()
