import os
import urllib.request
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def download_nse_universe(cache_dir: str, universe_url: str, logger: logging.Logger) -> list:
    """
    Downloads the official listed equities from NSE India.
    Saves a local copy and returns a list of dictionaries with company info.
    """
    cache_path = os.path.join(cache_dir, "nse_universe.csv")
    
    # Download file if not exists or if older than 24 hours
    should_download = True
    if os.path.exists(cache_path):
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        if datetime.now() - file_time < timedelta(hours=24):
            should_download = False
            logger.info("Using cached NSE universe list.")
            
    if should_download:
        logger.info(f"Downloading NSE universe list from: {universe_url}")
        try:
            req = urllib.request.Request(universe_url, headers=HEADERS)
            with urllib.request.urlopen(req) as response:
                html = response.read()
            with open(cache_path, "wb") as f:
                f.write(html)
        except Exception as e:
            logger.error(f"Failed to download NSE universe list: {e}")
            if os.path.exists(cache_path):
                logger.info("Falling back to existing cached list.")
            else:
                raise e

    # Read and parse the CSV
    df = pd.read_csv(cache_path)
    # Strip column names
    df.columns = [c.strip() for c in df.columns]
    
    universe = []
    for _, row in df.iterrows():
        symbol = str(row["SYMBOL"]).strip()
        name = str(row["NAME OF COMPANY"]).strip()
        series = str(row.get("SERIES", "EQ")).strip()
        
        # Yahoo Finance ticker symbol for NSE stocks is {SYMBOL}.NS
        yahoo_ticker = f"{symbol}.NS"
        
        universe.append({
            "symbol": yahoo_ticker,
            "nse_symbol": symbol,
            "name": name,
            "series": series
        })
        
    logger.info(f"NSE universe constructed with {len(universe)} symbols.")
    return universe

def download_stock_ohlcv(ticker: str, raw_dir: str, history_days: int) -> bool:
    """
    Downloads daily OHLCV for a single ticker.
    Supports incremental updates using local Parquet caching.
    """
    file_path = os.path.join(raw_dir, f"{ticker}.parquet")
    today = datetime.now().date()
    
    # We calculate the start date for full download (roughly 1.6 years to cover history_days trading days)
    # 400 trading days is ~600 calendar days
    calendar_days = int(history_days * 1.5)
    start_date = today - timedelta(days=calendar_days)
    
    df_old = None
    last_date = None
    
    # Check if we have cached data
    if os.path.exists(file_path):
        try:
            df_old = pd.read_parquet(file_path)
            if not df_old.empty and "Date" in df_old.columns:
                df_old["Date"] = pd.to_datetime(df_old["Date"]).dt.date
                df_old.set_index("Date", inplace=True)
            
            if not df_old.empty:
                last_date = df_old.index.max()
        except Exception:
            # If parquet is corrupted, we will do a clean download
            df_old = None
            last_date = None

    # Check if incremental download is needed
    if last_date is not None:
        # If the last date in cache is today or yesterday (and today is weekend/early morning), skip
        # Note: NSE closes at 3:30 PM, so new EOD data is available after that.
        if today - last_date <= timedelta(days=1) and datetime.now().hour < 18:
            return True
            
        # Download from the last date + 1 day to today
        fetch_start = last_date + timedelta(days=1)
        if fetch_start >= today:
            return True
            
        try:
            # Download new data
            # Use period="5d" or dates. dates are safer
            df_new = yf.download(ticker, start=fetch_start.strftime("%Y-%m-%d"), end=(today + timedelta(days=1)).strftime("%Y-%m-%d"), progress=False)
            if not df_new.empty:
                if isinstance(df_new.columns, pd.MultiIndex):
                    df_new.columns = df_new.columns.get_level_values(0)
                # Format index
                df_new.index = pd.to_datetime(df_new.index).date
                # Merge
                df_combined = pd.concat([df_old, df_new])
                # Drop duplicate index values, keeping the latest
                df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
                df_combined.sort_index(inplace=True)
                
                # Save
                df_combined.reset_index().rename(columns={"index": "Date"}).to_parquet(file_path, index=False)
                return True
            else:
                # No new data found, which is fine
                return True
        except Exception:
            # If incremental fetch fails, fallback to full download below
            pass

    # Full Download
    try:
        df_all = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), end=(today + timedelta(days=1)).strftime("%Y-%m-%d"), progress=False)
        if not df_all.empty:
            if isinstance(df_all.columns, pd.MultiIndex):
                df_all.columns = df_all.columns.get_level_values(0)
            df_all.index = pd.to_datetime(df_all.index).date
            df_all.reset_index().rename(columns={"index": "Date"}).to_parquet(file_path, index=False)
            return True
        return False
    except Exception:
        return False

def download_universe_history(tickers: list, raw_dir: str, history_days: int, max_workers: int, logger: logging.Logger):
    """
    Downloads EOD history for all tickers in parallel using ThreadPoolExecutor.
    """
    logger.info(f"Starting parallel EOD download for {len(tickers)} tickers with {max_workers} threads...")
    
    success_count = 0
    fail_count = 0
    
    # We use ThreadPoolExecutor to run downloads in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks
        futures = {executor.submit(download_stock_ohlcv, t, raw_dir, history_days): t for t in tickers}
        
        # Process as they complete with progress bar
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Downloading OHLCV"):
            ticker = futures[fut]
            try:
                success = fut.result()
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                
    logger.info(f"Parallel download finished. Successful: {success_count}, Failed/Skipped: {fail_count}.")
