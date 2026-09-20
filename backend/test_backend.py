import sys
import os

# Add parent directory to path so backend imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import scraper
from backend import analyzer

def run_tests():
    print("=== StonksAI Backend Tests ===")
    
    # Test 1: Autocomplete Search
    print("\n[Test 1] Testing search autocomplete for 'TATA'...")
    search_results = scraper.search_company("TATA")
    if search_results:
        print(f"Success! Found {len(search_results)} results. Top matches:")
        for res in search_results[:3]:
            symbol = res.get('url', '').split('/company/')[-1].split('/')[0]
            print(f"  - {res['name']} (Symbol: {symbol}, URL: {res['url']})")
    else:
        print("Failure! No search results returned.")
        return False
        
    # Test 2: Screener Scraping
    test_symbol = "TATASTEEL"
    print(f"\n[Test 2] Scraping fundamental data for '{test_symbol}'...")
    scraped_data = scraper.scrape_screener_data(test_symbol)
    if scraped_data and "quarterly_financials" in scraped_data:
        print("Success! Scraped fundamentals:")
        print(f"  - Sector: {scraped_data['sector']}")
        print(f"  - Industry: {scraped_data['industry']}")
        print(f"  - About: {scraped_data['about'][:150]}...")
        print(f"  - Financials Count: {len(scraped_data['quarterly_financials'])} quarters")
        if scraped_data['quarterly_financials']:
            print(f"  - Latest Quarter: {scraped_data['quarterly_financials'][-1]}")
        print(f"  - Peers Count: {len(scraped_data['peers'])} peer companies")
    else:
        print("Failure! Scraping returned empty or invalid data.")
        return False
        
    # Test 3: Yahoo Ticker Mapping
    print(f"\n[Test 3] Mapping '{test_symbol}' to Yahoo Finance ticker...")
    yahoo_symbol = analyzer.get_yahoo_ticker(test_symbol)
    print(f"Success! Mapped '{test_symbol}' -> '{yahoo_symbol}'")
    
    # Test 4: Relative Strength Calculations
    print(f"\n[Test 4] Calculating Relative Strength for '{yahoo_symbol}' vs Nifty 50...")
    rs_data = analyzer.calculate_relative_strength(yahoo_symbol)
    if rs_data and "returns" in rs_data:
        print("Success! Calculated RS metrics:")
        print(f"  - Current Price: Rs. {rs_data['current_price']}")
        print(f"  - RS Trend: {rs_data['rs_trend']}")
        print(f"  - Returns: 1M: {rs_data['returns']['1m']}, 3M: {rs_data['returns']['3m']}, 6M: {rs_data['returns']['6m']}, 1Y: {rs_data['returns']['1y']}")
        print(f"  - Chart Data Points: {len(rs_data['chart_data'])} points")
    else:
        print("Failure! RS calculation returned empty or invalid data.")
        return False
        
    print("\n=== All Tests Passed Successfully! ===")
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
