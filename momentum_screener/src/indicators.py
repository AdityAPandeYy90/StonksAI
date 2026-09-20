import pandas as pd
import numpy as np
import os

def calculate_rs_metrics(stock_df: pd.DataFrame, index_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """
    Calculates Relative Strength ratio, Mansfield RS, and Return Differences
    against a benchmark index and adds them to stock_df.
    """
    # Create copies to avoid SettingWithCopyWarning
    stock_df = stock_df.copy()
    index_df = index_df.copy()
    
    # Ensure Date columns are datetime and sorted
    stock_df["Date"] = pd.to_datetime(stock_df["Date"])
    index_df["Date"] = pd.to_datetime(index_df["Date"])
    
    index_df = index_df.sort_values("Date").drop_duplicates(subset=["Date"])
    
    # Merge stock and index data
    merged = pd.merge(stock_df, index_df[["Date", "Close"]], on="Date", suffixes=("", "_Index"), how="left")
    merged["Close_Index"] = merged["Close_Index"].ffill()
    
    # Ratios
    merged["Ratio"] = merged["Close"] / merged["Close_Index"]
    
    # Mansfield RS (50 days)
    merged["Ratio_SMA50"] = merged["Ratio"].rolling(window=50).mean()
    merged[f"RS_Mansfield_{prefix}"] = np.where(
        (merged["Ratio_SMA50"] > 0) & merged["Ratio_SMA50"].notna(),
        ((merged["Ratio"] / merged["Ratio_SMA50"]) - 1) * 100,
        np.nan
    )
    
    # RS Returns Difference
    for period, col_name in [(21, "1M"), (63, "3M"), (126, "6M"), (252, "1Y")]:
        stock_ret = merged["Close"].pct_change(periods=period) * 100
        index_ret = merged["Close_Index"].pct_change(periods=period) * 100
        merged[f"RS_Return_{col_name}_{prefix}"] = stock_ret - index_ret
        
    # Drop temp columns
    merged.drop(columns=["Close_Index", "Ratio", "Ratio_SMA50"], inplace=True, errors="ignore")
    return merged

def calculate_technical_indicators(file_path: str, history_days: int, index_dfs: dict = None, sector_index_ticker: str = None) -> pd.DataFrame:
    """
    Reads the parquet file for a stock, computes all Qullamaggie style 
    technical indicators, computes relative strength, and returns a DataFrame 
    with the latest row of data.
    """
    if not os.path.exists(file_path):
        return pd.DataFrame()
        
    df = pd.read_parquet(file_path)
    if df.empty:
        return pd.DataFrame()
        
    # Drop rows where prices are missing (e.g. empty weekend placeholder rows from yfinance)
    df.dropna(subset=["Close", "High", "Low", "Open"], inplace=True)
    
    if len(df) < 5:  # Need at least 5 bars for basic calculations
        return pd.DataFrame()
        
    # Ensure sorted by Date
    df.sort_values("Date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    # 1. Trend Moving Averages
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["SMA21"] = df["Close"].rolling(window=21).mean()
    df["SMA50"] = df["Close"].rolling(window=50).mean()
    df["SMA65"] = df["Close"].rolling(window=65).mean()
    df["SMA150"] = df["Close"].rolling(window=150).mean()
    df["SMA200"] = df["Close"].rolling(window=200).mean()
    df["SMA7"] = df["Close"].rolling(window=7).mean()
    
    # Trend Intensity (TI65)
    df["TI65"] = (df["SMA7"] / df["SMA65"]) * 100
    
    # 2. Volatility Indicators
    # True Range (TR)
    high_low = df["High"] - df["Low"]
    high_prevclose = (df["High"] - df["Close"].shift(1)).abs()
    low_prevclose = (df["Low"] - df["Close"].shift(1)).abs()
    df["TR"] = pd.concat([high_low, high_prevclose, low_prevclose], axis=1).max(axis=1)
    
    # Average True Range (ATR 21) using Wilder's EMA
    df["ATR21"] = df["TR"].ewm(alpha=1/21, adjust=False).mean()
    
    # ATR% (ATR as a percentage of price)
    df["ATR_pct"] = (df["ATR21"] / df["Close"]) * 100
    
    # ADR21 (Average Daily Range over 21 days as % of Low price)
    df["Daily_Range_pct"] = ((df["High"] - df["Low"]) / df["Low"]) * 100
    df["ADR21"] = df["Daily_Range_pct"].rolling(window=21).mean()
    
    # ADR20 (Average Daily Range over 20 days as % of Low price)
    df["ADR20"] = df["Daily_Range_pct"].rolling(window=20).mean()
    
    # 3. Liquidity Metrics
    df["Dollar_Volume"] = df["Close"] * df["Volume"]
    df["Avg_Dollar_Volume_50"] = df["Dollar_Volume"].rolling(window=50).mean()
    df["Avg_Volume_20"] = df["Volume"].rolling(window=20).mean()
    df["Avg_Volume_50"] = df["Volume"].rolling(window=50).mean()
    
    # Convert Avg Dollar Volume to Crores (1 Crore = 10,000,000)
    df["Avg_Dollar_Volume_Cr"] = df["Avg_Dollar_Volume_50"] / 10_000_000
    
    # 5-day average daily dollar volume (and in Crores)
    df["Avg_Dollar_Volume_5"] = df["Dollar_Volume"].rolling(window=5).mean()
    df["Avg_Dollar_Volume_5_Cr"] = df["Avg_Dollar_Volume_5"] / 10_000_000
    
    # 4. Return Calculations
    df["Return_1W"] = df["Close"].pct_change(periods=5) * 100
    df["Return_2W"] = df["Close"].pct_change(periods=10) * 100
    df["Return_1M"] = df["Close"].pct_change(periods=21) * 100
    df["Return_3M"] = df["Close"].pct_change(periods=63) * 100
    df["Return_6M"] = df["Close"].pct_change(periods=126) * 100
    df["Return_1Y"] = df["Close"].pct_change(periods=252) * 100
    df["Return_2Y"] = df["Close"].pct_change(periods=504) * 100
    
    # 5. Distance and Channel Metrics
    df["Dist_EMA21_pct"] = ((df["Close"] - df["EMA21"]) / df["EMA21"]) * 100
    df["Dist_SMA50_pct"] = ((df["Close"] - df["SMA50"]) / df["SMA50"]) * 100
    df["Dist_SMA200_pct"] = ((df["Close"] - df["SMA200"]) / df["SMA200"]) * 100
    
    # 52 Week Channel High & Low (approx 252 trading days)
    rolling_252 = df.rolling(window=min(252, len(df)))
    df["High_52W"] = rolling_252["High"].max()
    df["Low_52W"] = rolling_252["Low"].min()
    
    df["Dist_52W_High_pct"] = ((df["Close"] - df["High_52W"]) / df["High_52W"]) * 100
    df["Dist_52W_Low_pct"] = ((df["Close"] - df["Low_52W"]) / df["Low_52W"]) * 100
    
    # Price History Bars (Total trading days available)
    df["Price_History_Bars"] = len(df)
    
    # Default columns to NaN in case they aren't calculated
    rs_cols = [
        "RS_Mansfield_Nifty500", "RS_Return_1M_Nifty500", "RS_Return_3M_Nifty500", "RS_Return_6M_Nifty500", "RS_Return_1Y_Nifty500",
        "RS_Mansfield_Nifty50", "RS_Return_1M_Nifty50", "RS_Return_3M_Nifty50", "RS_Return_6M_Nifty50", "RS_Return_1Y_Nifty50",
        "RS_Mansfield_Sector", "RS_Return_1M_Sector", "RS_Return_3M_Sector", "RS_Return_6M_Sector", "RS_Return_1Y_Sector"
    ]
    for col in rs_cols:
        df[col] = np.nan
    df["Sector_Index_Used"] = "None"

    # 6. Relative Strength Calculations
    if index_dfs:
        # RS vs Nifty 500
        n500_df = index_dfs.get("^CRSLDX")
        if n500_df is not None and not n500_df.empty:
            df = calculate_rs_metrics(df, n500_df, "Nifty500")
            
        # RS vs Nifty 50
        n50_df = index_dfs.get("^NSEI")
        if n50_df is not None and not n50_df.empty:
            df = calculate_rs_metrics(df, n50_df, "Nifty50")
            
        # RS vs Sectoral Index
        if sector_index_ticker and sector_index_ticker in index_dfs:
            sect_df = index_dfs[sector_index_ticker]
            if sect_df is not None and not sect_df.empty:
                df = calculate_rs_metrics(df, sect_df, "Sector")
                df["Sector_Index_Used"] = sector_index_ticker

    # Return only the last row containing all calculated indicators
    return df.iloc[[-1]].copy()

def load_benchmark_indices(raw_dir: str, config: dict) -> dict:
    """
    Loads historical data for all configured benchmark indices.
    Returns a dict mapping ticker symbols to pd.DataFrame.
    """
    index_dfs = {}
    rs_config = config.get("relative_strength", {})
    if not rs_config:
        return index_dfs
        
    benchmarks = list(rs_config.get("benchmarks", {}).values()) + list(rs_config.get("sector_index_mapping", {}).values())
    benchmarks = list(set(benchmarks))
    
    for ticker in benchmarks:
        file_path = os.path.join(raw_dir, f"{ticker}.parquet")
        if os.path.exists(file_path):
            try:
                df = pd.read_parquet(file_path)
                if not df.empty and "Date" in df.columns:
                    index_dfs[ticker] = df
            except Exception:
                pass
    return index_dfs

def process_all_indicators(tickers_meta: list, raw_dir: str, history_days: int, sector_mapping: dict = None, config: dict = None) -> pd.DataFrame:
    """
    Computes technical indicators for all downloaded stocks.
    Aggregates the final metrics into a single pandas DataFrame.
    """
    processed_rows = []
    
    # Load index dataframes if config is provided
    index_dfs = None
    if config:
        index_dfs = load_benchmark_indices(raw_dir, config)
    
    for meta in tickers_meta:
        ticker = meta["symbol"]
        file_path = os.path.join(raw_dir, f"{ticker}.parquet")
        
        # Determine sectoral index
        nse_symbol = meta["nse_symbol"]
        sector_index_ticker = None
        if sector_mapping and nse_symbol in sector_mapping and config:
            stock_sector = str(sector_mapping[nse_symbol].get("sector", "")).upper()
            mapping = config.get("relative_strength", {}).get("sector_index_mapping", {})
            for key, val in mapping.items():
                if key.upper() in stock_sector:
                    sector_index_ticker = val
                    break
        
        try:
            latest_row = calculate_technical_indicators(
                file_path=file_path, 
                history_days=history_days,
                index_dfs=index_dfs,
                sector_index_ticker=sector_index_ticker
            )
            if not latest_row.empty:
                # Add metadata columns
                latest_row["Ticker"] = ticker
                latest_row["NSE_Symbol"] = meta["nse_symbol"]
                latest_row["Company"] = meta["name"]
                latest_row["Series"] = meta["series"]
                processed_rows.append(latest_row)
        except Exception:
            # Skip corrupted or error-prone rows silently
            pass
            
    if not processed_rows:
        return pd.DataFrame()
        
    # Concat all rows
    full_df = pd.concat(processed_rows, ignore_index=True)
    return full_df

