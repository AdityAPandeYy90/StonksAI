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
from src.filters import apply_screener_filters, run_easy_scans, apply_multilevel_sector_filter
from src.export import export_watchlists, export_easy_scans, export_filtered_stocks
from src.sector import get_sector_industry_mapping

def run_screener():
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
    logger.info("        StonksAI - Indian Momentum Screener        ")
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
    
    # 6. Calculate Technical Indicators
    logger.info("Calculating technical indicators & relative strength for all downloaded stocks...")
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
    
    # 7. Percentile Ranking & Momentum Scoring
    logger.info("Percentile ranking stocks and calculating Weighted Momentum Scores...")
    df_ranked = rank_universe_momentum(df_indicators, config)
    
    # 8. Apply Screener Filters (Liquidity, Price, ATR%, Trends)
    logger.info("Applying stock criteria filters...")
    df_filtered = apply_screener_filters(df_ranked, config, logger)
    
    if df_filtered.empty:
        logger.warning("No stocks passed the filtering criteria. Watchlists will be empty.")
        
    # 9. Slice and Export Watchlists (Original)
    logger.info("Slicing watchlists and writing export spreadsheets...")
    export_watchlists(
        df=df_filtered,
        output_dir=paths["output_dir"],
        config=config,
        logger=logger
    )
    
    # 10. Run and Export 8 custom EasyScans
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"Running 8 custom EasyScans with timestamp: {timestamp_str}...")
    easy_scans_results = run_easy_scans(df_ranked, config, logger)
    export_easy_scans(easy_scans_results, paths["output_dir"], timestamp_str, logger)
    
    # 11. Multi-Level Stock Filtering & Sector Hierarchy Export
    logger.info("Running Multi-Level Stock Filtering & Sector Hierarchy Analysis...")
    scan_symbols = set()
    for df_scan in easy_scans_results.values():
        if not df_scan.empty and "NSE_Symbol" in df_scan.columns:
            scan_symbols.update(df_scan["NSE_Symbol"].dropna().unique())
    candidate_tickers = list(scan_symbols)
    sector_mapping = get_sector_industry_mapping(candidate_tickers, paths["cache_dir"], logger)
    
    df_multi_filtered, df_sector_summary = apply_multilevel_sector_filter(
        easy_scans_results=easy_scans_results,
        df_ranked=df_ranked,
        config=config,
        sector_mapping=sector_mapping,
        logger=logger
    )
    
    export_filtered_stocks(
        df_filtered=df_multi_filtered,
        df_sector_summary=df_sector_summary,
        output_dir=paths["output_dir"],
        logger=logger
    )
    
    end_time = time.time()
    elapsed_minutes = (end_time - start_time) / 60
    
    logger.info("===================================================")
    logger.info("          Screener Run Completed!                 ")
    logger.info(f"Total Elapsed Time: {elapsed_minutes:.1f} minutes")
    logger.info(f"Watchlists & EasyScans Saved to: {paths['output_dir']}")
    logger.info("===================================================")

if __name__ == "__main__":
    run_screener()
