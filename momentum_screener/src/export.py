import os
import pandas as pd
import json
import logging
from datetime import datetime

def export_watchlists(df: pd.DataFrame, output_dir: str, config: dict, logger: logging.Logger) -> dict:
    """
    Slices the stock lists by top % (e.g. 7%), extracts the intersection,
    and exports spreadsheets, JSONs, and TradingView watchlists.
    """
    if df.empty:
        logger.warning("Empty DataFrame provided to exporter. Skipping exports.")
        return {}
        
    top_pct = float(config.get("top_percent", 7.0)) / 100.0
    total_stocks = len(df)
    slice_size = max(1, int(total_stocks * top_pct))
    
    # 1. Slice Top Stocks for each category
    # Combined Momentum (Sorted by Momentum Score)
    combined_list = df.sort_values("Momentum_Score", ascending=False).head(slice_size)
    
    # 1M Momentum (Sorted by Rank1M)
    m1_list = df.sort_values("Rank1M", ascending=False).head(slice_size)
    
    # 3M Momentum (Sorted by Rank3M)
    m3_list = df.sort_values("Rank3M", ascending=False).head(slice_size)
    
    # 6M Momentum (Sorted by Rank6M)
    m6_list = df.sort_values("Rank6M", ascending=False).head(slice_size)
    
    # Intersection List (stocks that are in m1_list, m3_list, AND m6_list)
    m1_symbols = set(m1_list["NSE_Symbol"])
    m3_symbols = set(m3_list["NSE_Symbol"])
    m6_symbols = set(m6_list["NSE_Symbol"])
    
    intersection_symbols = m1_symbols.intersection(m3_symbols).intersection(m6_symbols)
    intersection_list = df[df["NSE_Symbol"].isin(intersection_symbols)].sort_values("Momentum_Score", ascending=False)
    
    # Define columns to keep for Excel/CSV outputs
    columns_to_keep = [
        "NSE_Symbol", "Company", "Close", "Momentum_Score", "Rank1M", "Rank3M", "Rank6M",
        "RS_Mansfield_Nifty500", "Rank_RS_Nifty500", "RS_Mansfield_Nifty50", "Rank_RS_Nifty50",
        "RS_Mansfield_Sector", "Rank_RS_Sector", "Sector_Index_Used",
        "ATR_pct", "ADR21", "Avg_Dollar_Volume_Cr", 
        "Dist_EMA21_pct", "Dist_SMA50_pct", "Dist_SMA200_pct", "Dist_52W_High_pct"
    ]
    
    # Check if columns exist (safety check)
    output_cols = [col for col in columns_to_keep if col in df.columns]
    
    lists_dict = {
        "combined_momentum": combined_list[output_cols],
        "1m_momentum": m1_list[output_cols],
        "3m_momentum": m3_list[output_cols],
        "6m_momentum": m6_list[output_cols],
        "intersection": intersection_list[output_cols]
    }
    
    # Log counts
    logger.info(f"Screener compiled watchlists (Top {config.get('top_percent')}% = {slice_size} stocks):")
    logger.info(f"  - Combined Momentum: {len(combined_list)} stocks")
    logger.info(f"  - 1M Momentum: {len(m1_list)} stocks")
    logger.info(f"  - 3M Momentum: {len(m3_list)} stocks")
    logger.info(f"  - 6M Momentum: {len(m6_list)} stocks")
    logger.info(f"  - Intersection (in all 3): {len(intersection_list)} stocks")
    
    # 2. Export Excel Workbook (Multi-tab)
    excel_path = os.path.join(output_dir, "momentum_watchlist.xlsx")
    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for sheet_name, data in lists_dict.items():
                # Clean sheet name for excel (max 31 chars)
                clean_name = sheet_name.replace("_", " ").title()[:30]
                data.to_excel(writer, sheet_name=clean_name, index=False)
        logger.info(f"Exported multi-sheet Excel to: {excel_path}")
    except Exception as e:
        logger.error(f"Failed to export Excel workbook: {e}")
        
    # 3. Export CSV, JSON, and TradingView Watchlists
    for list_name, data in lists_dict.items():
        # Clean CSV / JSON paths
        csv_path = os.path.join(output_dir, f"{list_name}.csv")
        json_path = os.path.join(output_dir, f"{list_name}.json")
        tv_path = os.path.join(output_dir, f"tradingview_{list_name}.txt")
        
        # Save CSV & JSON
        try:
            data.to_csv(csv_path, index=False)
            data.to_json(json_path, orient="records", indent=4)
        except Exception as e:
            logger.error(f"Failed to export CSV/JSON for {list_name}: {e}")
            
        # Save TradingView format (NSE:SYMBOL)
        try:
            # Series prefixing: standard equities get NSE: prefix.
            # E.g. SBIN -> NSE:SBIN
            symbols_list = [f"NSE:{sym}" for sym in data["NSE_Symbol"].tolist() if pd.notna(sym)]
            tv_content = ",".join(symbols_list)
            
            with open(tv_path, "w", encoding="utf-8") as f:
                f.write(tv_content)
        except Exception as e:
            logger.error(f"Failed to export TradingView list for {list_name}: {e}")
            
    logger.info(f"Watchlist files saved to: {output_dir}")
    return lists_dict


def export_easy_scans(scans_dict: dict, output_dir: str, timestamp_str: str, logger: logging.Logger) -> None:
    """
    Exports the results of the 8 TC2000 EasyScans as separate CSV, JSON, 
    and TradingView text files, with name format SetupName_YYYYMMDD_HHMMSS.ext.
    Also packs them all into a multi-tab Excel spreadsheet.
    """
    if not scans_dict:
        logger.warning("No scan results to export.")
        return

    # Create output subfolder if needed
    os.makedirs(output_dir, exist_ok=True)
    
    # Write multi-tab Excel
    excel_path = os.path.join(output_dir, f"easy_scans_watchlist_{timestamp_str}.xlsx")
    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for scan_name, df_scan in scans_dict.items():
                # Clean sheet name for excel (max 31 chars)
                clean_name = scan_name.replace("_", " ").title()[:30]
                df_scan.to_excel(writer, sheet_name=clean_name, index=False)
        logger.info(f"Exported combined EasyScans Excel to: {excel_path}")
    except Exception as e:
        logger.error(f"Failed to export EasyScans Excel workbook: {e}")

    # Write separate CSV, JSON, and TradingView files
    for scan_name, df_scan in scans_dict.items():
        csv_path = os.path.join(output_dir, f"{scan_name}_{timestamp_str}.csv")
        json_path = os.path.join(output_dir, f"{scan_name}_{timestamp_str}.json")
        tv_path = os.path.join(output_dir, f"tradingview_{scan_name}_{timestamp_str}.txt")

        # Save CSV & JSON
        try:
            df_scan.to_csv(csv_path, index=False)
            df_scan.to_json(json_path, orient="records", indent=4)
        except Exception as e:
            logger.error(f"Failed to export CSV/JSON for scan {scan_name}: {e}")

        # Save TradingView format (NSE:SYMBOL)
        try:
            symbols_list = [f"NSE:{sym}" for sym in df_scan["NSE_Symbol"].tolist() if pd.notna(sym)]
            tv_content = ",".join(symbols_list)
            with open(tv_path, "w", encoding="utf-8") as f:
                f.write(tv_content)
        except Exception as e:
            logger.error(f"Failed to export TradingView list for scan {scan_name}: {e}")

    logger.info(f"All EasyScan files exported successfully with timestamp {timestamp_str}.")


def export_filtered_stocks(df_filtered: pd.DataFrame, df_sector_summary: pd.DataFrame, output_dir: str, logger: logging.Logger) -> tuple:
    """
    Exports the multi-level filtered stocks to:
    - filtered_stocks_DD-MM-YYYY.xlsx (Multi-tab Excel with 'Filtered Stocks' and 'Sector & Industry Summary')
    - filtered_stocks_DD-MM-YYYY.csv (CSV file)
    - tradingview_filtered_stocks_DD-MM-YYYY.txt (TradingView watchlist format)
    Returns (excel_path, csv_path).
    """
    if df_filtered.empty:
        logger.warning("No filtered stocks to export.")
        return "", ""

    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%d-%m-%Y")

    excel_path = os.path.join(output_dir, f"filtered_stocks_{date_str}.xlsx")
    csv_path = os.path.join(output_dir, f"filtered_stocks_{date_str}.csv")
    tv_path = os.path.join(output_dir, f"tradingview_filtered_stocks_{date_str}.txt")

    # 1. Export Excel Workbook
    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df_filtered.to_excel(writer, sheet_name="Filtered Stocks", index=False)
            if not df_sector_summary.empty:
                df_sector_summary.to_excel(writer, sheet_name="Sector & Industry Summary", index=False)
        logger.info(f"Exported multi-tab Filtered Stocks Excel to: {excel_path}")
    except Exception as e:
        logger.error(f"Failed to export Filtered Stocks Excel: {e}")

    # 2. Export CSV File
    try:
        df_filtered.to_csv(csv_path, index=False)
        logger.info(f"Exported Filtered Stocks CSV to: {csv_path}")
    except Exception as e:
        logger.error(f"Failed to export Filtered Stocks CSV: {e}")

    # 3. Export TradingView Watchlist File
    try:
        col = "NSE_Symbol" if "NSE_Symbol" in df_filtered.columns else "symbol"
        symbols = [f"NSE:{sym}" for sym in df_filtered[col].dropna() if str(sym).strip()]
        tv_content = ",".join(symbols)
        with open(tv_path, "w", encoding="utf-8") as f:
            f.write(tv_content)
        logger.info(f"Exported TradingView list to: {tv_path}")
    except Exception as e:
        logger.error(f"Failed to export TradingView list for filtered stocks: {e}")

    return excel_path, csv_path


