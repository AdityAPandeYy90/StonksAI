import os
import sys
import time
from datetime import datetime

# Add the src folder to path so main can import them
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src.utils import load_config, setup_directories, setup_logger
from src.download import download_nse_universe, download_universe_history
from src.indicators import process_all_indicators
from src.ranking import rank_universe_momentum
from src.filters import apply_screener_filters
from src.export import export_watchlists
from src.sector import get_sector_industry_mapping

def run_rs_screener():
    # 1. Load Configurations
    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading configurations: {e}")
        sys.exit(1)
        
    # 2. Setup Directories
    paths = setup_directories(config)
    
    # 3. Setup Logger
    logger = setup_logger(paths["log_dir"])
    logger.info("===================================================")
    logger.info("        StonksAI - Indian Relative Strength Screener ")
    logger.info("===================================================")
    logger.info(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    start_time = time.time()
    
    # 4. Build Stock Universe
    try:
        universe = download_nse_universe(
            cache_dir=paths["cache_dir"],
            universe_url=config["universe_url"],
            logger=logger
        )
    except Exception as e:
        logger.critical(f"Critical error constructing stock universe: {e}")
        sys.exit(1)
        
    # Extract ticker list
    tickers = [item["symbol"] for item in universe]
    
    # 5. Parallel OHLCV Download
    logger.info("Initializing parallel historical OHLCV download...")
    download_universe_history(
        tickers=tickers,
        raw_dir=paths["raw_dir"],
        history_days=config.get("history_days", 400),
        max_workers=config.get("parallel_downloads", 15),
        logger=logger
    )
    
    # Download benchmark indices
    rs_config = config.get("relative_strength", {})
    if rs_config:
        benchmarks = list(rs_config.get("benchmarks", {}).values()) + list(rs_config.get("sector_index_mapping", {}).values())
        benchmarks = list(set(benchmarks))
        logger.info(f"Downloading {len(benchmarks)} benchmark indices for Relative Strength calculations...")
        download_universe_history(
            tickers=benchmarks,
            raw_dir=paths["raw_dir"],
            history_days=config.get("history_days", 400),
            max_workers=5,
            logger=logger
        )
        
    # Load Sector/Industry Mapping for the entire universe (instant since cached)
    logger.info("Loading Sector & Industry classifications...")
    sector_mapping = get_sector_industry_mapping(tickers, paths["cache_dir"], logger)
    
    # 6. Calculate Technical Indicators & Relative Strength
    logger.info("Calculating technical indicators & relative strength for all stocks...")
    df_indicators = process_all_indicators(
        tickers_meta=universe,
        raw_dir=paths["raw_dir"],
        history_days=config.get("history_days", 400),
        sector_mapping=sector_mapping,
        config=config
    )
    
    if df_indicators.empty:
        logger.error("No stock price data was successfully loaded or processed. Screener halted.")
        sys.exit(1)
        
    logger.info(f"Successfully calculated indicators for {len(df_indicators)} stocks.")
    
    # 7. Percentile Ranking & Momentum/RS Scoring
    logger.info("Percentile ranking stocks and calculating Relative Strength ranks...")
    df_ranked = rank_universe_momentum(df_indicators, config)
    
    # 8. Apply Relative Strength Filters
    logger.info("Applying Relative Strength screening criteria...")
    # Apply standard price/liquidity filters first
    df_base_filtered = apply_screener_filters(df_ranked, config, logger)
    
    if df_base_filtered.empty:
        logger.warning("No stocks passed the base filtering criteria. RS screens will be empty.")
        sys.exit(0)
        
    # Now filter specifically for High Relative Strength (e.g. Mansfield RS > 0 and Rank_RS_Nifty500 >= 80)
    # This filters for stocks that are actively outperforming the broad market.
    rs_n500_threshold = rs_config.get("min_rs_rank_nifty500", 80.0)
    
    df_rs_filtered = df_base_filtered[
        (df_base_filtered["RS_Mansfield_Nifty500"] > 0) & 
        (df_base_filtered["Rank_RS_Nifty500"] >= rs_n500_threshold)
    ].copy()
    
    logger.info(f"RS Filter (Mansfield Nifty500 > 0 & Rank >= {rs_n500_threshold}): kept {len(df_rs_filtered)} / {len(df_base_filtered)} stocks.")
    
    # 9. Slice and Export RS Watchlists
    logger.info("Slicing watchlists and writing exports...")
    date_str = datetime.now().strftime("%d-%m-%Y")
    
    # Define columns to keep for Excel/CSV outputs
    columns_to_keep = [
        "NSE_Symbol", "Company", "Close", "Momentum_Score", "Rank1M", "Rank3M", "Rank6M",
        "RS_Mansfield_Nifty500", "Rank_RS_Nifty500", "RS_Mansfield_Nifty50", "Rank_RS_Nifty50",
        "RS_Mansfield_Sector", "Rank_RS_Sector", "Sector_Index_Used",
        "ATR_pct", "ADR21", "Avg_Dollar_Volume_Cr", 
        "Dist_EMA21_pct", "Dist_SMA50_pct", "Dist_SMA200_pct", "Dist_52W_High_pct"
    ]
    output_cols = [col for col in columns_to_keep if col in df_rs_filtered.columns]
    
    # Sort by RS Rank vs Nifty 500
    df_rs_sorted = df_rs_filtered.sort_values("Rank_RS_Nifty500", ascending=False)
    
    # Prepare exports dict
    lists_dict = {
        "rs_leaders": df_rs_sorted[output_cols],
        "rs_sector_leaders": df_rs_sorted[df_rs_sorted["Rank_RS_Sector"] >= 80][output_cols] if "Rank_RS_Sector" in df_rs_sorted.columns else df_rs_sorted[output_cols]
    }
    
    # Multi-tab Excel named: rs_watchlist_DD-MM-YYYY.xlsx
    excel_name = f"rs_watchlist_{date_str}.xlsx"
    excel_path = os.path.join(paths["output_dir"], excel_name)
    try:
        import pandas as pd
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for sheet_name, data in lists_dict.items():
                clean_name = sheet_name.replace("_", " ").title()[:30]
                data.to_excel(writer, sheet_name=clean_name, index=False)
        logger.info(f"Exported Relative Strength watchlists to Excel: {excel_path}")
    except Exception as e:
        logger.error(f"Failed to export Excel workbook: {e}")
        
    # Export CSV, JSON, and TradingView Watchlists
    for list_name, data in lists_dict.items():
        csv_path = os.path.join(paths["output_dir"], f"{list_name}_{date_str}.csv")
        json_path = os.path.join(paths["output_dir"], f"{list_name}_{date_str}.json")
        tv_path = os.path.join(paths["output_dir"], f"tradingview_{list_name}_{date_str}.txt")
        
        try:
            data.to_csv(csv_path, index=False)
            data.to_json(json_path, orient="records", indent=4)
            
            # TradingView Watchlist format
            symbols_list = [f"NSE:{sym}" for sym in data["NSE_Symbol"].tolist() if pd.notna(sym)]
            tv_content = ",".join(symbols_list)
            with open(tv_path, "w", encoding="utf-8") as f:
                f.write(tv_content)
        except Exception as e:
            logger.error(f"Failed to export outputs for {list_name}: {e}")
            
    end_time = time.time()
    elapsed_minutes = (end_time - start_time) / 60
    
    logger.info("===================================================")
    logger.info("       Relative Strength Screener Run Completed!   ")
    logger.info(f"Total Elapsed Time: {elapsed_minutes:.1f} minutes")
    logger.info(f"RS Watchlists Saved to: {paths['output_dir']}")
    logger.info("===================================================")

if __name__ == "__main__":
    run_rs_screener()
