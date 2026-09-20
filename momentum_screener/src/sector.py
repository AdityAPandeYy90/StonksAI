import os
import json
import logging
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_single_sector_industry(symbol: str) -> tuple:
    """
    Attempts to fetch Sector and Industry for a given NSE symbol.
    First tries Screener.in HTML parsing (tailored to Indian market), 
    then falls back to yfinance.
    Returns (clean_sym, sector, industry).
    """
    clean_sym = symbol.replace(".NS", "").strip().upper()
    sector = "Unknown"
    industry = "Unknown"
    
    # 1. Try Screener.in first (best for NSE stocks)
    try:
        url = f"https://www.screener.in/company/{clean_sym}/"
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            peers_section = soup.find("section", id="peers")
            if peers_section:
                sec_link = peers_section.find("a", title=re.compile(r"Sector", re.I))
                ind_link = peers_section.find("a", title=re.compile(r"Industry", re.I))
                if sec_link:
                    sector = sec_link.get_text(strip=True)
                if ind_link:
                    industry = ind_link.get_text(strip=True)
            if sector == "Unknown" or industry == "Unknown":
                sec_link = soup.find("a", title=re.compile(r"Sector", re.I))
                ind_link = soup.find("a", title=re.compile(r"Industry", re.I))
                if sec_link and sector == "Unknown":
                    sector = sec_link.get_text(strip=True)
                if ind_link and industry == "Unknown":
                    industry = ind_link.get_text(strip=True)
    except Exception:
        pass

    if sector != "Unknown" and industry != "Unknown":
        return clean_sym, sector, industry

    # 2. Fallback to yfinance if Screener.in was missing data
    try:
        import yfinance as yf
        yf_ticker = f"{clean_sym}.NS"
        ticker_obj = yf.Ticker(yf_ticker)
        # Try fast_info first to avoid crumb issues
        sec = getattr(ticker_obj, "fast_info", {}).get("sector", None)
        if not sec:
            info = ticker_obj.info
            sec = info.get("sector")
            ind = info.get("industry")
            if sec and sec != "None":
                sector = sec
            if ind and ind != "None":
                industry = ind
    except Exception:
        pass
        
    return clean_sym, sector, industry

def get_sector_industry_mapping(symbols: list, cache_dir: str, logger: logging.Logger) -> dict:
    """
    Loads sector and industry mapping for a list of NSE symbols.
    Uses local JSON caching at data/cache/sector_industry_mapping.json.
    Fetches missing symbols in parallel.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "sector_industry_mapping.json")
    
    mapping = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load sector mapping cache: {e}")
            mapping = {}
            
    # Clean symbol list
    symbols_to_check = [s.replace(".NS", "").strip().upper() for s in symbols]
    missing_symbols = [s for s in symbols_to_check if s not in mapping or mapping[s].get("sector") == "Unknown"]
    
    if missing_symbols:
        logger.info(f"Fetching Sector/Industry info for {len(missing_symbols)} candidate stocks...")
        updated = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_single_sector_industry, sym): sym for sym in missing_symbols}
            for fut in as_completed(futures):
                try:
                    sym, sec, ind = fut.result()
                    mapping[sym] = {
                        "sector": sec,
                        "industry": ind
                    }
                    updated += 1
                except Exception as err:
                    sym = futures[fut]
                    mapping[sym] = {"sector": "Unknown", "industry": "Unknown"}

        # Save updated mapping to cache
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2)
            logger.info(f"Updated sector mapping cache for {updated} stocks.")
        except Exception as e:
            logger.error(f"Failed to save sector mapping cache: {e}")
            
    return mapping

def enrich_df_with_sectors(df, mapping: dict):
    """
    Adds 'Sector' and 'Industry' columns to a pandas DataFrame based on 'NSE_Symbol' or 'symbol'.
    """
    if df.empty:
        df["Sector"] = []
        df["Industry"] = []
        return df

    sym_col = "NSE_Symbol" if "NSE_Symbol" in df.columns else ("symbol" if "symbol" in df.columns else None)
    if not sym_col:
        df["Sector"] = "Unknown"
        df["Industry"] = "Unknown"
        return df

    sectors = []
    industries = []
    for sym in df[sym_col]:
        clean_sym = str(sym).replace(".NS", "").strip().upper()
        info = mapping.get(clean_sym, {})
        sectors.append(info.get("sector", "Unknown"))
        industries.append(info.get("industry", "Unknown"))

    df = df.copy()
    df["Sector"] = sectors
    df["Industry"] = industries
    return df
