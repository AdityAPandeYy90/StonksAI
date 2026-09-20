import sys
import os
import unittest
import pandas as pd
import numpy as np

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src.utils import load_config, setup_directories
from src.download import download_nse_universe, download_stock_ohlcv
from src.indicators import calculate_technical_indicators
from src.ranking import rank_universe_momentum
from src.filters import apply_screener_filters, run_easy_scans
from src.export import export_watchlists, export_easy_scans


class TestMomentumScreener(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Load config and setup directory
        cls.config = load_config()
        # Override paths to test outputs so we don't mess up main dirs
        cls.config["data_dir"] = "test_data_dir"
        cls.config["output_dir"] = "test_output_dir"
        cls.config["log_dir"] = "test_log_dir"
        
        # Setup directories
        cls.paths = setup_directories(cls.config)
        
        import logging
        cls.logger = logging.getLogger("TestLogger")
        cls.logger.setLevel(logging.INFO)
        if not cls.logger.handlers:
            cls.logger.addHandler(logging.StreamHandler(sys.stdout))
            
    def test_01_universe_download(self):
        print("\n--- Test 1: Universe Download ---")
        universe = download_nse_universe(
            cache_dir=self.paths["cache_dir"],
            universe_url=self.config["universe_url"],
            logger=self.logger
        )
        self.assertGreater(len(universe), 0)
        self.assertIn("symbol", universe[0])
        self.assertTrue(universe[0]["symbol"].endswith(".NS"))
        
    def test_02_yfinance_download(self):
        print("\n--- Test 2: yfinance Download ---")
        # Test download of two stable tickers
        success1 = download_stock_ohlcv("TATASTEEL.NS", self.paths["raw_dir"], 200)
        success2 = download_stock_ohlcv("RELIANCE.NS", self.paths["raw_dir"], 200)
        self.assertTrue(success1)
        self.assertTrue(success2)
        
        # Verify parquet files exist
        self.assertTrue(os.path.exists(os.path.join(self.paths["raw_dir"], "TATASTEEL.NS.parquet")))
        self.assertTrue(os.path.exists(os.path.join(self.paths["raw_dir"], "RELIANCE.NS.parquet")))
        
    def test_03_indicator_calculations(self):
        print("\n--- Test 3: Indicator Calculation ---")
        file_path = os.path.join(self.paths["raw_dir"], "TATASTEEL.NS.parquet")
        df_indicators = calculate_technical_indicators(file_path, 200)
        
        self.assertFalse(df_indicators.empty)
        # Check standard columns
        self.assertIn("EMA21", df_indicators.columns)
        self.assertIn("SMA50", df_indicators.columns)
        self.assertIn("SMA200", df_indicators.columns)
        self.assertIn("ATR_pct", df_indicators.columns)
        self.assertIn("ADR21", df_indicators.columns)
        self.assertIn("ADR20", df_indicators.columns)
        self.assertIn("Avg_Dollar_Volume_Cr", df_indicators.columns)
        self.assertIn("Avg_Dollar_Volume_5_Cr", df_indicators.columns)
        self.assertIn("Return_1M", df_indicators.columns)
        self.assertIn("Return_2Y", df_indicators.columns)
        self.assertIn("Dist_52W_High_pct", df_indicators.columns)
        self.assertIn("TI65", df_indicators.columns)
        self.assertIn("Price_History_Bars", df_indicators.columns)
        
    def test_04_percentile_ranking(self):
        print("\n--- Test 4: Percentile Ranking ---")
        # Create a mock DataFrame with returns
        mock_data = pd.DataFrame({
            "Return_1M": [10.0, 50.0, -5.0, 20.0, 100.0],
            "Return_3M": [15.0, 60.0, -10.0, 25.0, 120.0],
            "Return_6M": [20.0, 70.0, -15.0, 30.0, 150.0],
            "Return_1Y": [10.0, 50.0, -5.0, 20.0, 100.0],
            "Return_2Y": [15.0, 60.0, -10.0, 25.0, 120.0],
        })
        df_ranked = rank_universe_momentum(mock_data, self.config)
        
        # Check ranks
        self.assertIn("Rank1M", df_ranked.columns)
        self.assertIn("Rank3M", df_ranked.columns)
        self.assertIn("Rank6M", df_ranked.columns)
        self.assertIn("Rank1Y", df_ranked.columns)
        self.assertIn("Rank2Y", df_ranked.columns)
        self.assertIn("Momentum_Score", df_ranked.columns)
        
        # Highest return should have rank 100
        self.assertEqual(df_ranked.iloc[4]["Rank1M"], 100.0)
        # Lowest return should have rank 20.0 (since rank is 1/5 = 20th percentile)
        self.assertEqual(df_ranked.iloc[2]["Rank1M"], 20.0)
        
    def test_05_filtering_and_export(self):
        print("\n--- Test 5: Filtering and Export ---")
        # Create mock ranked indicators
        mock_processed = pd.DataFrame({
            "NSE_Symbol": ["TATASTEEL", "RELIANCE", "MOCK1", "MOCK2"],
            "Company": ["Tata Steel", "Reliance Industries", "Mock Inc 1", "Mock Inc 2"],
            "Close": [150.0, 2500.0, 50.0, 1200.0],  # Mock1 will fail Price filter (< 100)
            "Avg_Dollar_Volume_Cr": [100.0, 500.0, 20.0, 5.0], # Mock2 will fail Liquidity filter (< 75 Cr)
            "ATR_pct": [3.5, 2.8, 1.2, 4.2], # Mock1 would fail ATR% (< 2.5) if it wasn't already filtered
            "EMA21": [140.0, 2400.0, 48.0, 1100.0],
            "SMA50": [135.0, 2300.0, 45.0, 1050.0],
            "SMA200": [120.0, 2100.0, 40.0, 950.0],
            "Rank1M": [80.0, 90.0, 20.0, 60.0],
            "Rank3M": [85.0, 92.0, 25.0, 62.0],
            "Rank6M": [75.0, 95.0, 15.0, 65.0],
            "Momentum_Score": [80.0, 92.3, 20.0, 62.3]
        })
        
        # Apply filters
        df_filtered = apply_screener_filters(mock_processed, self.config, self.logger)
        
        # Mock1 (price 50 < 100) and Mock2 (liquidity 5 < 75) should be filtered out
        filtered_symbols = df_filtered["NSE_Symbol"].tolist()
        self.assertIn("TATASTEEL", filtered_symbols)
        self.assertIn("RELIANCE", filtered_symbols)
        self.assertNotIn("MOCK1", filtered_symbols)
        self.assertNotIn("MOCK2", filtered_symbols)
        
        # Test exports
        exports = export_watchlists(df_filtered, self.paths["output_dir"], self.config, self.logger)
        self.assertIn("combined_momentum", exports)
        self.assertTrue(os.path.exists(os.path.join(self.paths["output_dir"], "momentum_watchlist.xlsx")))
        self.assertTrue(os.path.exists(os.path.join(self.paths["output_dir"], "combined_momentum.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.paths["output_dir"], "tradingview_combined_momentum.txt")))

    def test_06_easy_scans(self):
        print("\n--- Test 6: EasyScans Filtering and Export ---")
        # Mock ranked indicators with columns needed for EasyScans
        mock_data = pd.DataFrame({
            "NSE_Symbol": ["TATASTEEL", "RELIANCE", "MOCK_IPO", "MOCK_LOSER", "MOCK_OTC"],
            "Company": ["Tata Steel", "Reliance Industries", "Mock IPO", "Mock Loser", "Mock OTC"],
            "Close": [150.0, 2500.0, 120.0, 80.0, 15.0],
            "Volume": [100000, 500000, 40000, 30000, 80000],
            "Dollar_Volume": [150.0 * 100000, 2500.0 * 500000, 120.0 * 40000, 80.0 * 30000, 15.0 * 80000],
            "Avg_Dollar_Volume_Cr": [15.0, 125.0, 0.48, 0.24, 0.12],
            "Avg_Dollar_Volume_5_Cr": [15.0, 125.0, 0.48, 0.24, 0.12],
            "TI65": [105.0, 110.0, 100.0, 85.0, 98.0],
            "ADR20": [2.5, 3.2, 3.2, 1.5, 4.0],
            "Rank1M": [80.0, 98.5, 50.0, 2.0, 40.0],
            "Rank1Y": [70.0, 95.0, 45.0, 1.5, 30.0],
            "Rank2Y": [65.0, 92.0, 40.0, 1.2, 25.0],
            "Return_1W": [5.0, 25.0, 2.0, -8.0, 3.0],
            "Price_History_Bars": [500, 500, 50, 500, 500]
        })
        
        # Test scans execution
        scans_results = run_easy_scans(mock_data, self.config, self.logger)
        
        # Verify keys are present
        self.assertIn("recent_ipos", scans_results)
        self.assertIn("biggest_1m_gainers", scans_results)
        self.assertIn("biggest_1y_losers", scans_results)
        self.assertIn("five_day_gainers", scans_results)
        self.assertIn("adr_scan", scans_results)
        self.assertIn("high_trend_intensity", scans_results)
        self.assertIn("biggest_2y_losers", scans_results)
        self.assertIn("otc_scan", scans_results)
        
        # Verify MOCK_IPO is found in recent_ipos (since history_bars <= 250 and other criteria met)
        recent_ipo_symbols = scans_results["recent_ipos"]["NSE_Symbol"].tolist()
        self.assertIn("MOCK_IPO", recent_ipo_symbols)
        
        # Verify MOCK_LOSER is found in biggest_1y_losers
        loser_symbols = scans_results["biggest_1y_losers"]["NSE_Symbol"].tolist()
        self.assertIn("MOCK_LOSER", loser_symbols)
        
        # Verify MOCK_OTC is in otc_scan
        otc_symbols = scans_results["otc_scan"]["NSE_Symbol"].tolist()
        self.assertIn("MOCK_OTC", otc_symbols)
        
        # Test export
        timestamp = "20260710_182318"
        export_easy_scans(scans_results, self.paths["output_dir"], timestamp, self.logger)
        
        # Verify some files are written
        self.assertTrue(os.path.exists(os.path.join(self.paths["output_dir"], f"easy_scans_watchlist_{timestamp}.xlsx")))
        self.assertTrue(os.path.exists(os.path.join(self.paths["output_dir"], f"recent_ipos_{timestamp}.csv")))

    def test_07_multilevel_filtering_and_export(self):
        print("\n--- Test 7: Multi-Level Sector Filtering and Export ---")
        from src.filters import apply_multilevel_sector_filter
        from src.export import export_filtered_stocks

        mock_scans = {
            "adr_scan": pd.DataFrame({"NSE_Symbol": ["TATASTEEL", "RELIANCE", "MOCK_SOLO"]}),
            "high_trend_intensity": pd.DataFrame({"NSE_Symbol": ["TATASTEEL", "RELIANCE"]}),
            "five_day_gainers": pd.DataFrame({"NSE_Symbol": ["TATASTEEL"]})
        }
        mock_ranked = pd.DataFrame({
            "NSE_Symbol": ["TATASTEEL", "RELIANCE", "MOCK_SOLO"],
            "Company": ["Tata Steel", "Reliance Industries", "Solo Company"],
            "Close": [150.0, 2500.0, 100.0],
            "TI65": [115.0, 110.0, 105.0]
        })
        mock_sector_map = {
            "TATASTEEL": {"sector": "Basic Materials", "industry": "Steel"},
            "RELIANCE": {"sector": "Energy", "industry": "Oil & Gas"},
            "MOCK_SOLO": {"sector": "Industrials", "industry": "Machinery"}
        }

        df_filtered, df_summary = apply_multilevel_sector_filter(
            easy_scans_results=mock_scans,
            df_ranked=mock_ranked,
            config=self.config,
            sector_mapping=mock_sector_map,
            logger=self.logger
        )

        filtered_syms = df_filtered["NSE_Symbol"].tolist()
        self.assertIn("TATASTEEL", filtered_syms)
        self.assertIn("RELIANCE", filtered_syms)
        self.assertNotIn("MOCK_SOLO", filtered_syms) # Score 1 should be deleted

        # TATASTEEL matched 3 scans, RELIANCE matched 2 scans
        tatasteel_row = df_filtered[df_filtered["NSE_Symbol"] == "TATASTEEL"].iloc[0]
        self.assertEqual(tatasteel_row["Scan_Score"], 3)

        # Verify summary
        self.assertFalse(df_summary.empty)
        self.assertIn("Broader Sector", df_summary.columns)
        self.assertIn("Finer Industry", df_summary.columns)

        # Test export
        excel_path, csv_path = export_filtered_stocks(df_filtered, df_summary, self.paths["output_dir"], self.logger)
        self.assertTrue(os.path.exists(excel_path))
        self.assertTrue(os.path.exists(csv_path))


    @classmethod
    def tearDownClass(cls):
        # Clean up test directories
        import shutil
        for name, path in cls.paths.items():
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                except Exception:
                    pass
        # Clean up parent test folders
        for folder in ["test_data_dir", "test_output_dir", "test_log_dir"]:
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder)
                except Exception:
                    pass

if __name__ == "__main__":
    unittest.main()
