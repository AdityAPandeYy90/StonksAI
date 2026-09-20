import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def search_company(query: str, session=None):
    """
    Search Screener.in's autocomplete search API.
    Returns a list of dicts with company metadata.
    """
    url = f"https://www.screener.in/api/company/search/?q={query}"
    try:
        response = (session or requests).get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"Error searching company: {e}")
        return []

def clean_value(val_str: str) -> float:
    """Helper to parse a string value into a clean float or return None."""
    if not val_str or val_str.strip() in ("", "-", "—", "N/A"):
        return None
    # Remove commas and percentage signs
    cleaned = re.sub(r"[^\d\.\-]", "", val_str)
    try:
        return float(cleaned) if "." in cleaned else int(cleaned)
    except ValueError:
        return None

def scrape_screener_data(symbol: str, session=None):
    """
    Scrapes quarterly results, peer comparison, and about details for the given symbol.
    """
    ticker = re.sub(r"[^A-Za-z0-9]", "", symbol).upper()
    url = f"https://www.screener.in/company/{ticker}/"
    
    try:
        response = (session or requests).get(url, headers=HEADERS, timeout=4)
        if response.status_code in (429, 403):
            raise Exception(f"Screener.in rate limited (HTTP {response.status_code})")
        if response.status_code != 200:
            url = f"https://www.screener.in/company/{ticker}/consolidated/"
            response = (session or requests).get(url, headers=HEADERS, timeout=4)
            if response.status_code in (429, 403):
                raise Exception(f"Screener.in rate limited (HTTP {response.status_code})")
            if response.status_code != 200:
                raise Exception(f"Failed to fetch Screener page, status: {response.status_code}")

        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # 1. Extract About / Company Profile
        about_text = ""
        profile_div = soup.find("div", class_="company-profile")
        if not profile_div:
            # Fallback to class about
            profile_div = soup.find("div", class_="about")
        if profile_div:
            about_text = profile_div.get_text(separator=" ", strip=True)
            # Remove "read more" if present
            about_text = re.sub(r"\s*Read More\s*$", "", about_text, flags=re.IGNORECASE)
            # Standardize spacing
            about_text = " ".join(about_text.split())
            
        # 2. Extract Sector, Industry, and Current Price
        sector = "Unknown"
        industry = "Unknown"
        current_price = None
        
        top_ratios = soup.find_all("li")
        for li in top_ratios:
            text = li.get_text(separator=" ", strip=True)
            if "Current Price" in text and current_price is None:
                val_span = li.find("span", class_="number")
                if val_span:
                    current_price = clean_value(val_span.get_text(strip=True))
        
        peers_section = soup.find("section", id="peers")
        if peers_section:
            sector_link = peers_section.find("a", title=re.compile(r"Sector", re.I))
            industry_link = peers_section.find("a", title=re.compile(r"Industry", re.I))
            if sector_link:
                sector = sector_link.get_text(strip=True)
            if industry_link:
                industry = industry_link.get_text(strip=True)
        
        # Fallback to general page search if not found in peers_section
        if sector == "Unknown" or industry == "Unknown":
            sector_link = soup.find("a", title=re.compile(r"Sector", re.I))
            industry_link = soup.find("a", title=re.compile(r"Industry", re.I))
            if sector_link and sector == "Unknown":
                sector = sector_link.get_text(strip=True)
            if industry_link and industry == "Unknown":
                industry = industry_link.get_text(strip=True)

        # 3. Extract Quarterly Results Table
        quarters_section = soup.find("section", id="quarters")
        quarterly_data = []
        if quarters_section:
            table = quarters_section.find("table")
            if table:
                thead = table.find("thead")
                tbody = table.find("tbody")
                
                # Extract quarter headers (column names)
                headers = []
                if thead:
                    headers = [th.get_text(strip=True) for th in thead.find_all("th") if th.get_text(strip=True)]
                else:
                    # Fallback to first row
                    first_row = table.find("tr")
                    if first_row:
                        headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"]) if th.get_text(strip=True)]
                
                # Clean headers, the first column is the label, others are quarters
                quarter_names = [h for h in headers if h not in ("Sales", "Net Profit", "EPS", "Expenses", "Other Income", "Interest", "Depreciation", "Tax")]
                
                rows_dict = {}
                if tbody:
                    for tr in tbody.find_all("tr"):
                        tds = tr.find_all(["td", "th"])
                        if not tds:
                            continue
                        row_label = tds[0].get_text(strip=True).replace("\n", "").replace("+", "").strip()
                        row_vals = [td.get_text(strip=True) for td in tds[1:]]
                        rows_dict[row_label] = row_vals
                
                # Check for standard names
                sales_vals = None
                net_profit_vals = None
                eps_vals = None
                
                # Support fallbacks for banks/financials where "Sales" is "Revenue" or "Interest"
                for label in ("sales", "revenue", "interest"):
                    for key, val in rows_dict.items():
                        if key.lower().strip() == label:
                            sales_vals = val
                            break
                    if sales_vals is not None:
                        break
                        
                for key, val in rows_dict.items():
                    key_lower = key.lower().strip()
                    if key_lower == "net profit":
                        net_profit_vals = val
                    elif key_lower in ("eps in rs", "eps"):
                        eps_vals = val

                # We need the last 6 quarters
                # Determine how many columns of data we have
                num_quarters = len(quarter_names)
                
                # Reconstruct quarterly metrics
                quarters_list = []
                for i in range(num_quarters):
                    q_name = quarter_names[i] if i < len(quarter_names) else f"Q{i+1}"
                    
                    sales = clean_value(sales_vals[i]) if sales_vals and i < len(sales_vals) else None
                    net_profit = clean_value(net_profit_vals[i]) if net_profit_vals and i < len(net_profit_vals) else None
                    eps = clean_value(eps_vals[i]) if eps_vals and i < len(eps_vals) else None
                    
                    # Calculate Net Profit Margin (NPM %)
                    npm_pct = None
                    if sales and net_profit and sales > 0:
                        npm_pct = round((net_profit / sales) * 100, 2)
                        
                    quarters_list.append({
                        "quarter": q_name,
                        "sales": sales,
                        "net_profit": net_profit,
                        "npm_percent": npm_pct,
                        "eps": eps
                    })
                
                # Take the last 12 quarters to allow YoY (4 quarters back) and QoQ calculations
                quarterly_data = quarters_list[-12:]
                
        # 4. Extract Peers Table
        peers_list = []
        warehouse_div = soup.find(attrs={"data-warehouse-id": True})
        if warehouse_div:
            warehouse_id = warehouse_div["data-warehouse-id"]
            peers_url = f"https://www.screener.in/api/company/{warehouse_id}/peers/"
            try:
                peers_resp = (session or requests).get(peers_url, headers=HEADERS, timeout=10)
                if peers_resp.status_code == 200:
                    peers_soup = BeautifulSoup(peers_resp.content, "html.parser")
                    peers_table = peers_soup.find("table")
                    if peers_table:
                        thead = peers_table.find("thead")
                        tbody = peers_table.find("tbody")
                        
                        # Get column headers
                        col_headers = []
                        if thead:
                            col_headers = [th.get_text(strip=True) for th in thead.find_all("th")]
                        else:
                            first_tr = peers_table.find("tr")
                            if first_tr:
                                col_headers = [th.get_text(strip=True) for th in first_tr.find_all(["th", "td"])]
                        
                        # Find indices dynamically based on headers
                        name_idx = 1
                        cmp_idx = 2
                        pe_idx = 3
                        mc_idx = 4
                        div_idx = 5
                        np_idx = 6
                        sales_idx = 8
                        
                        for i, h in enumerate(col_headers):
                            h_clean = h.lower().replace(" ", "").replace(".", "")
                            if "name" in h_clean:
                                name_idx = i
                            elif "cmp" in h_clean:
                                cmp_idx = i
                            elif "p/e" in h_clean or "pe" in h_clean:
                                pe_idx = i
                            elif "marcap" in h_clean or "marketcap" in h_clean:
                                mc_idx = i
                            elif "div" in h_clean:
                                div_idx = i
                            elif "npqtr" in h_clean or "netprofitqtr" in h_clean or "profitqtr" in h_clean:
                                np_idx = i
                            elif "salesqtr" in h_clean or "revenueqtr" in h_clean:
                                sales_idx = i
                                
                        if tbody:
                            for tr in tbody.find_all("tr"):
                                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                                if len(tds) <= max(name_idx, cmp_idx, pe_idx, mc_idx, div_idx, np_idx, sales_idx):
                                    continue
                                
                                # Extract peer symbol
                                name_cell = tr.find_all("td")[name_idx]
                                link = name_cell.find("a")
                                peer_symbol = ""
                                if link and "href" in link.attrs:
                                    href_parts = [p for p in link["href"].split("/") if p]
                                    if "company" in href_parts:
                                        idx = href_parts.index("company")
                                        if idx + 1 < len(href_parts):
                                            peer_symbol = href_parts[idx + 1]
                                    else:
                                        peer_symbol = link["href"].split("/company/")[-1].replace("/", "")
                                
                                peer_dict = {
                                    "name": name_cell.get_text(strip=True).replace("\n", "").strip(),
                                    "symbol": peer_symbol,
                                    "cmp": clean_value(tds[cmp_idx]),
                                    "pe": clean_value(tds[pe_idx]),
                                    "market_cap_cr": clean_value(tds[mc_idx]),
                                    "div_yield_percent": clean_value(tds[div_idx]),
                                    "net_profit_qtr_cr": clean_value(tds[np_idx]),
                                    "sales_qtr_cr": clean_value(tds[sales_idx])
                                }
                                peers_list.append(peer_dict)
            except Exception as e:
                print(f"Error fetching peers API: {e}")
                        
        return {
            "symbol": ticker,
            "about": about_text,
            "sector": sector,
            "industry": industry,
            "current_price": current_price,
            "quarterly_financials": quarterly_data,
            "peers": peers_list
        }
        
    except Exception as e:
        print(f"Error scraping Screener data: {e}")
        return {
            "symbol": symbol,
            "about": "Could not fetch company profile.",
            "sector": "Unknown",
            "industry": "Unknown",
            "quarterly_financials": [],
            "peers": [],
            "error": str(e)
        }

if __name__ == "__main__":
    # Test scrape
    print("Searching for Reliance...")
    res = search_company("Reliance")
    print("Search Results:", res[:3])
    if res:
        print("Scraping Reliance...")
        data = scrape_screener_data("RELIANCE")
        print("Sector:", data["sector"])
        print("Quarters:", data["quarterly_financials"])
        print("Peers count:", len(data["peers"]))
