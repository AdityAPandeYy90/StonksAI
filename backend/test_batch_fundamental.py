import os
import sys
import unittest
import pandas as pd
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import main
from backend import scraper

class TestBatchFundamentalScreening(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Create a mock spreadsheet containing symbols
        cls.test_dir = os.path.dirname(os.path.abspath(__file__))
        cls.mock_excel_path = os.path.join(cls.test_dir, "test_watchlist_input.xlsx")
        
        df = pd.DataFrame({
            "NSE_Symbol": ["RELIANCE", "TCS", "TATAMOTORS", "INFY", "MOCKFAIL"],
            "Company": ["Reliance Industries", "TCS", "Tata Motors", "Infosys", "Mock Failure Inc"]
        })
        df.to_excel(cls.mock_excel_path, index=False)
        print(f"Created mock input Excel at: {cls.mock_excel_path}")

    def test_01_extract_symbols(self):
        print("\n--- Test 1: Extracting Tickers from Excel ---")
        symbols = main.extract_symbols_from_files([self.mock_excel_path])
        self.assertEqual(len(symbols), 5)
        self.assertIn("RELIANCE", symbols)
        self.assertIn("TCS", symbols)
        self.assertIn("MOCKFAIL", symbols)
        print("Successfully extracted symbols:", symbols)

    def test_02_qoq_evaluation_logic(self):
        print("\n--- Test 2: QoQ Evaluation Logic (Mock Scraping) ---")
        # Define mock rules
        rules = {
            "min_eps_growth_qoq": 2.0,
            "min_sales_growth_qoq": 1.0,
            "min_npm_percent": 10.0,
            "allow_missing_yoy_for_ipos": True
        }
        
        # Test a mock evaluation for a passing company
        passed_eval = main.evaluate_stock_fundamentals("RELIANCE", rules)
        print(f"Reliance Eval -> Passed: {passed_eval['passed']}, Reason: {passed_eval['reason']}")
        self.assertIn("passed", passed_eval)
        self.assertIn("metrics", passed_eval)
        
        # Test a mock evaluation for an invalid company (should fail gracefully)
        failed_eval = main.evaluate_stock_fundamentals("MOCKFAIL", rules)
        print(f"MockFail Eval -> Passed: {failed_eval['passed']}, Reason: {failed_eval['reason']}")
        self.assertFalse(failed_eval["passed"])
        self.assertTrue("Failed to fetch data" in failed_eval["reason"] or "fallback failed" in failed_eval["reason"])

    def test_03_batch_screening_run_and_excel_output(self):
        print("\n--- Test 3: Batch Screening Run & Excel Writing ---")
        # Read from mock excel and run screening logic manually
        symbols = main.extract_symbols_from_files([self.mock_excel_path])
        rules = {
            "min_eps_growth_qoq": 0.0,
            "min_sales_growth_qoq": 0.0,
            "min_npm_percent": 8.0,
            "allow_missing_yoy_for_ipos": True
        }
        
        results = []
        # We will screen RELIANCE and TCS to keep it simple and avoid rate limiting
        for sym in ["RELIANCE", "TCS"]:
            eval_res = main.evaluate_stock_fundamentals(sym, rules)
            results.append(eval_res)
            
        passed_rows = []
        rejected_rows = []
        for r in results:
            row_data = {
                "Symbol": r["symbol"],
                "Company Name": r["company_name"],
                "Sector": r["metrics"].get("Sector", "Unknown"),
                "Industry": r["metrics"].get("Industry", "Unknown"),
                "Market Cap (Cr)": r["metrics"].get("Market_Cap_Cr"),
            }
            for idx in range(3):
                row_data[f"Q{idx} Quarter"] = r["metrics"].get(f"Q{idx}_Quarter")
                row_data[f"Q{idx} Sales (Cr)"] = r["metrics"].get(f"Q{idx}_Sales_Cr")
                row_data[f"Q{idx} Sales QoQ %"] = r["metrics"].get(f"Q{idx}_Sales_QoQ%")
                row_data[f"Q{idx} NPM %"] = r["metrics"].get(f"Q{idx}_NPM%")
                row_data[f"Q{idx} EPS (₹)"] = r["metrics"].get(f"Q{idx}_EPS")
                row_data[f"Q{idx} EPS QoQ %"] = r["metrics"].get(f"Q{idx}_EPS_QoQ%")
                
            row_data["Pass/Fail"] = "Pass" if r["passed"] else "Fail"
            row_data["Reason"] = r["reason"]
            
            if r["passed"]:
                passed_rows.append(row_data)
            else:
                rejected_rows.append(row_data)
                
        # Standard Excel column headers
        excel_cols = [
            "Symbol", "Company Name", "Sector", "Industry", "Market Cap (Cr)",
            "Q0 Quarter", "Q0 Sales (Cr)", "Q0 Sales QoQ %", "Q0 NPM %", "Q0 EPS (₹)", "Q0 EPS QoQ %",
            "Q1 Quarter", "Q1 Sales (Cr)", "Q1 Sales QoQ %", "Q1 NPM %", "Q1 EPS (₹)", "Q1 EPS QoQ %",
            "Q2 Quarter", "Q2 Sales (Cr)", "Q2 Sales QoQ %", "Q2 NPM %", "Q2 EPS (₹)", "Q2 EPS QoQ %",
            "Pass/Fail", "Reason"
        ]

        # Validate Excel writing
        strong_path = os.path.join(main.OUTPUTS_DIR, "test_Strong_Fundamentals.xlsx")
        rejected_path = os.path.join(main.OUTPUTS_DIR, "test_Rejected.xlsx")
        
        df_passed = pd.DataFrame(passed_rows, columns=excel_cols)
        df_rejected = pd.DataFrame(rejected_rows, columns=excel_cols)
        
        summary_df = pd.DataFrame()
        if passed_rows:
            summary_df = df_passed.groupby("Sector").agg(
                Count=("Symbol", "count"),
                Avg_Market_Cap_Cr=("Market Cap (Cr)", "mean"),
                Avg_NPM_Q0=("Q0 NPM %", "mean")
            ).reset_index()
            
        with pd.ExcelWriter(strong_path, engine="openpyxl") as writer:
            df_passed.to_excel(writer, sheet_name="Fundamentals", index=False)
            summary_df.to_excel(writer, sheet_name="Market View", index=False)
            
        with pd.ExcelWriter(rejected_path, engine="openpyxl") as writer:
            df_rejected.to_excel(writer, sheet_name="Rejected", index=False)
            
        self.assertTrue(os.path.exists(strong_path))
        self.assertTrue(os.path.exists(rejected_path))
        
        # Verify columns in written sheets
        df_read_strong = pd.read_excel(strong_path, sheet_name="Fundamentals")
        self.assertIn("Symbol", df_read_strong.columns)
        self.assertIn("Q0 Sales QoQ %", df_read_strong.columns)
        self.assertIn("Sector", df_read_strong.columns)
        
        # Clean up test files
        os.remove(strong_path)
        os.remove(rejected_path)
        print("Success! Excel file headers and tabs were validated successfully.")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.mock_excel_path):
            os.remove(cls.mock_excel_path)
            print("Cleaned up mock Excel file.")

if __name__ == "__main__":
    unittest.main()
