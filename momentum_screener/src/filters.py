import pandas as pd
import logging

def apply_screener_filters(df: pd.DataFrame, config: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Applies price, liquidity, volatility, and trend filters to the stock universe.
    Returns the filtered DataFrame.
    """
    if df.empty:
        return df
        
    initial_count = len(df)
    filtered_df = df.copy()
    
    # 1. Price Filter (default >= 100)
    min_price = float(config.get("min_price", 100.0))
    filtered_df = filtered_df[filtered_df["Close"] >= min_price]
    price_count = len(filtered_df)
    logger.info(f"Price filter (>= Rs. {min_price}): kept {price_count} / {initial_count} stocks.")
    
    # 2. Liquidity Filter (default Average Dollar Volume >= 75 Crores)
    min_vol_cr = float(config.get("min_dollar_volume_cr", 75.0))
    filtered_df = filtered_df[filtered_df["Avg_Dollar_Volume_Cr"] >= min_vol_cr]
    liq_count = len(filtered_df)
    logger.info(f"Liquidity filter (Avg Daily Dollar Vol >= Rs. {min_vol_cr} Cr): kept {liq_count} / {price_count} stocks.")
    
    # 3. Volatility Filter (default ATR% >= 2.5%)
    min_atr = float(config.get("min_atr_percent", 2.5))
    filtered_df = filtered_df[filtered_df["ATR_pct"] >= min_atr]
    vol_count = len(filtered_df)
    logger.info(f"Volatility filter (ATR% >= {min_atr}%): kept {vol_count} / {liq_count} stocks.")
    
    # 4. Trend Filters (Price > EMA21 * 1.01, Price > SMA50 * 1.01, Price > SMA200 * 1.01)
    # Ensure they exist in the columns before filtering
    for ema_col in ["EMA21", "SMA50", "SMA200"]:
        if ema_col in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["Close"] > filtered_df[ema_col] * 1.01]
            
    trend_count = len(filtered_df)
    logger.info(f"Trend uptrend filters (Price > 21EMA/50SMA/200SMA by 1%): kept {trend_count} / {vol_count} stocks.")
    
    return filtered_df


def run_easy_scans(df: pd.DataFrame, config: dict, logger: logging.Logger) -> dict:
    """
    Runs the 8 custom EasyScans on the ranked DataFrame based on the configuration settings.
    Returns a dictionary of DataFrames, where the key is the scan name.
    """
    if df.empty:
        return {}

    scans_config = config.get("scans", {})
    if not scans_config:
        logger.warning("No 'scans' configuration found in settings.yaml.")
        return {}

    results = {}
    
    # Columns to keep for EasyScans exports
    columns_to_keep = [
        "NSE_Symbol", "Company", "Close", "Volume", "TI65", "ADR20", "Rank1M", "Rank1Y", "Rank2Y",
        "Avg_Dollar_Volume_Cr", "Avg_Dollar_Volume_5_Cr", "Dollar_Volume",
        "Dist_EMA21_pct", "Dist_SMA50_pct", "Dist_SMA200_pct"
    ]
    output_cols = [c for c in columns_to_keep if c in df.columns]

    for scan_name, params in scans_config.items():
        scan_df = df.copy()
        
        # 1. Universe Filter
        if params.get("universe") == "nifty_500":
            # Proxy Nifty 500 by top 500 stocks by 50-day average daily dollar volume
            if "Avg_Dollar_Volume_Cr" in scan_df.columns:
                scan_df = scan_df.sort_values("Avg_Dollar_Volume_Cr", ascending=False).head(500)
        
        # 2. Min Price
        if "min_price" in params and "Close" in scan_df.columns:
            scan_df = scan_df[scan_df["Close"] >= float(params["min_price"])]
            
        # 3. Max Price
        if "max_price" in params and "Close" in scan_df.columns:
            scan_df = scan_df[scan_df["Close"] <= float(params["max_price"])]
            
        # 4. Volume
        if "min_volume" in params and "Volume" in scan_df.columns:
            scan_df = scan_df[scan_df["Volume"] >= float(params["min_volume"])]
            
        # 5. 1-Day Dollar Volume (in Crores)
        if "min_dollar_volume_cr" in params and "Dollar_Volume" in scan_df.columns:
            min_val = float(params["min_dollar_volume_cr"]) * 10_000_000
            scan_df = scan_df[scan_df["Dollar_Volume"] >= min_val]
            
        # 6. 5-Day Avg Dollar Volume (in Crores)
        if "min_5d_dollar_volume_cr" in params and "Avg_Dollar_Volume_5_Cr" in scan_df.columns:
            scan_df = scan_df[scan_df["Avg_Dollar_Volume_5_Cr"] >= float(params["min_5d_dollar_volume_cr"])]
            
        # 7. ADR20
        if "min_adr20" in params and "ADR20" in scan_df.columns:
            scan_df = scan_df[scan_df["ADR20"] >= float(params["min_adr20"])]
            
        # 8. Trend Intensity
        if "min_trend_intensity" in params and "TI65" in scan_df.columns:
            scan_df = scan_df[scan_df["TI65"] >= float(params["min_trend_intensity"])]
            
        # 9. Rank 1M
        if "min_rank_1m" in params and "Rank1M" in scan_df.columns:
            scan_df = scan_df[scan_df["Rank1M"] >= float(params["min_rank_1m"])]
            
        # 10. Max Rank 1Y (for losers)
        if "max_rank_1y" in params and "Rank1Y" in scan_df.columns:
            scan_df = scan_df[scan_df["Rank1Y"] <= float(params["max_rank_1y"])]
            
        # 11. Max Rank 2Y (for losers)
        if "max_rank_2y" in params and "Rank2Y" in scan_df.columns:
            scan_df = scan_df[scan_df["Rank2Y"] <= float(params["max_rank_2y"])]
            
        # 12. 5-Day Return (Return_1W)
        if "min_5d_return" in params and "Return_1W" in scan_df.columns:
            scan_df = scan_df[scan_df["Return_1W"] >= float(params["min_5d_return"])]
            
        # 13. History Bars Min/Max
        if "min_history_bars" in params and "Price_History_Bars" in scan_df.columns:
            scan_df = scan_df[scan_df["Price_History_Bars"] >= float(params["min_history_bars"])]
            
        if "max_history_bars" in params and "Price_History_Bars" in scan_df.columns:
            scan_df = scan_df[scan_df["Price_History_Bars"] <= float(params["max_history_bars"])]

        # Sort scan results
        if "max_rank_1y" in params or "max_rank_2y" in params:
            sort_col = "Rank1Y" if "max_rank_1y" in params else "Rank2Y"
            if sort_col in scan_df.columns:
                scan_df = scan_df.sort_values(sort_col, ascending=True)
        else:
            sort_col = "TI65" if "TI65" in scan_df.columns else "Close"
            scan_df = scan_df.sort_values(sort_col, ascending=False)

        logger.info(f"Scan '{scan_name}': kept {len(scan_df)} stocks.")
        results[scan_name] = scan_df[output_cols]

    return results


def apply_multilevel_sector_filter(easy_scans_results: dict, df_ranked: pd.DataFrame, config: dict, sector_mapping: dict, logger: logging.Logger) -> tuple:
    """
    Level 1: Union of candidates across all EasyScans.
    Level 2: Merge duplicate occurrences, calculate Scan_Score, filter out Score < min_scan_score (default 2).
    Level 3: Enrich with Sector & Industry hierarchy, generate hierarchical summary DataFrame.
             Optionally filter by top N sectors if auto_filter_top_sectors is True.
    Returns (df_filtered_stocks, df_sector_summary).
    """
    if not easy_scans_results or df_ranked.empty:
        logger.warning("Empty EasyScans or ranked DataFrame. Multi-level filtering skipped.")
        return pd.DataFrame(), pd.DataFrame()

    min_score = int(config.get("min_scan_score", 2))
    auto_filter_sectors = config.get("auto_filter_top_sectors", False)
    top_sectors_count = int(config.get("top_sectors_count", 3))

    # 1. Level 1 & Level 2: Collect scan matches for each stock symbol
    symbol_scans = {}
    for scan_name, scan_df in easy_scans_results.items():
        if scan_df.empty:
            continue
        col = "NSE_Symbol" if "NSE_Symbol" in scan_df.columns else "symbol"
        for sym in scan_df[col].dropna():
            clean_sym = str(sym).replace(".NS", "").strip().upper()
            if clean_sym not in symbol_scans:
                symbol_scans[clean_sym] = []
            if scan_name not in symbol_scans[clean_sym]:
                symbol_scans[clean_sym].append(scan_name)

    level1_count = len(symbol_scans)
    logger.info(f"Level 1: Found {level1_count} unique candidate stocks across all EasyScans.")

    # 2. Filter by minimum scan score (Level 2)
    filtered_symbol_info = {}
    for sym, scans in symbol_scans.items():
        score = len(scans)
        if score >= min_score:
            filtered_symbol_info[sym] = {
                "Scan_Score": score,
                "Scans_Matched": ", ".join(scans)
            }

    level2_count = len(filtered_symbol_info)
    logger.info(f"Level 2: Filtered out stocks with Scan_Score < {min_score}. Retained {level2_count} / {level1_count} stocks.")

    if not filtered_symbol_info:
        logger.warning(f"No stocks met the minimum Scan Score threshold of {min_score}.")
        return pd.DataFrame(), pd.DataFrame()

    # 3. Pull full stock metrics from df_ranked
    sym_col = "NSE_Symbol" if "NSE_Symbol" in df_ranked.columns else "symbol"
    df_ranked_clean = df_ranked.copy()
    df_ranked_clean["clean_sym"] = df_ranked_clean[sym_col].astype(str).str.replace(".NS", "").str.strip().str.upper()

    passing_syms = set(filtered_symbol_info.keys())
    df_pass = df_ranked_clean[df_ranked_clean["clean_sym"].isin(passing_syms)].copy()

    # Add Scan_Score and Scans_Matched
    df_pass["Scan_Score"] = df_pass["clean_sym"].map(lambda s: filtered_symbol_info[s]["Scan_Score"])
    df_pass["Scans_Matched"] = df_pass["clean_sym"].map(lambda s: filtered_symbol_info[s]["Scans_Matched"])

    # 4. Enrich with Sector and Industry
    from src.sector import enrich_df_with_sectors
    df_pass = enrich_df_with_sectors(df_pass, sector_mapping)

    # Clean up helper column
    df_pass.drop(columns=["clean_sym"], inplace=True, errors="ignore")

    # Reorder columns to put Sector, Industry, Scan_Score, Scans_Matched up front
    front_cols = ["NSE_Symbol", "Company", "Sector", "Industry", "Scan_Score", "Scans_Matched", "Close"]
    other_cols = [c for c in df_pass.columns if c not in front_cols]
    ordered_cols = [c for c in front_cols if c in df_pass.columns] + other_cols
    df_pass = df_pass[ordered_cols]

    # Sort Level 2 results by Scan_Score descending, then TI65/Momentum_Score
    sort_by = ["Scan_Score"]
    if "Momentum_Score" in df_pass.columns:
        sort_by.append("Momentum_Score")
    elif "TI65" in df_pass.columns:
        sort_by.append("TI65")

    df_pass.sort_values(by=sort_by, ascending=False, inplace=True)

    # 5. Build Level 3 Sector & Industry Summary DataFrame
    summary_rows = []
    grouped = df_pass.groupby(["Sector", "Industry"])
    for (sec, ind), group in grouped:
        symbols_str = ", ".join(group["NSE_Symbol"].dropna().tolist())
        summary_rows.append({
            "Broader Sector": sec,
            "Finer Industry": ind,
            "Stock Count": len(group),
            "Stocks Included": symbols_str
        })

    df_sector_summary = pd.DataFrame(summary_rows)
    if not df_sector_summary.empty:
        df_sector_summary.sort_values(by=["Stock Count", "Broader Sector"], ascending=[False, True], inplace=True)

    # 6. Apply Level 3 Top Sectors Filter if auto_filter_top_sectors is True
    if auto_filter_sectors and not df_sector_summary.empty:
        top_industries = set(df_sector_summary.head(top_sectors_count)["Finer Industry"])
        df_pass = df_pass[df_pass["Industry"].isin(top_industries)].copy()
        logger.info(f"Level 3: Automatically filtered to top {top_sectors_count} industries. Retained {len(df_pass)} stocks.")

    return df_pass, df_sector_summary


