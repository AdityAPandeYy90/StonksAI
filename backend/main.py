import socket
socket.setdefaulttimeout(4.0)  # Force OS-level TCP socket timeout to 4.0s for all network operations

from fastapi import FastAPI, Query, Header, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List, Optional, Any
import os
import json
import re
import datetime
import math
import requests
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from dotenv import load_dotenv

try:
    import pandas as pd
except ImportError:
    pd = None

def is_not_na(val):
    if val is None:
        return False
    if isinstance(val, float) and math.isnan(val):
        return False
    return True

def get_yahoo_price(symbol: str):
    """Fetch current stock price via lightweight Yahoo HTTP API without heavy yfinance/pandas dependencies."""
    ticker = f"{symbol.upper()}.NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=3.5)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                if price:
                    return round(float(price), 2)
    except Exception:
        pass
    return None

# Import our custom modules
from backend import scraper

# Load environment variables
load_dotenv()

from fastapi import FastAPI, Query, Header, HTTPException, File, UploadFile, Form

app = FastAPI(title="Indian Stock Fundamental & News Analyzer")

@app.get("/")
def read_root():
    root_html = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(root_html):
        return FileResponse(root_html, media_type="text/html")
    frontend_html = os.path.join(BASE_DIR, "frontend", "index.html")
    if os.path.exists(frontend_html):
        return FileResponse(frontend_html, media_type="text/html")
    return {"message": "StonksAI API is running"}

@app.get("/style.css")
@app.get("/api/style.css")
def serve_style_css():
    css_path = os.path.join(BASE_DIR, "style.css")
    if not os.path.exists(css_path):
        css_path = os.path.join(BASE_DIR, "frontend", "style.css")
    return FileResponse(css_path, media_type="text/css")

@app.get("/app.js")
@app.get("/api/app.js")
def serve_app_js():
    js_path = os.path.join(BASE_DIR, "app.js")
    if not os.path.exists(js_path):
        js_path = os.path.join(BASE_DIR, "frontend", "app.js")
    return FileResponse(js_path, media_type="application/javascript")

# Configure CORS so we can develop frontend independently if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".html", ".css")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENER_OUTPUTS_DIR = os.path.join(BASE_DIR, "momentum_screener", "outputs")

IS_VERCEL = "VERCEL" in os.environ
if IS_VERCEL:
    OUTPUTS_DIR = "/tmp/outputs"
else:
    OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

try:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
except Exception:
    OUTPUTS_DIR = "/tmp/outputs"
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

CACHE_DIR = os.path.join(OUTPUTS_DIR, "stock_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except Exception:
    pass

RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fundamental_rules.json")
USE_SCREENER_IN = True

def load_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "min_eps_growth_qoq": 0.0,
        "min_sales_growth_qoq": 0.0,
        "min_npm_percent": 8.0,
        "allow_missing_yoy_for_ipos": True
    }

def extract_from_df(df, symbols_set: set):
    target_col = None
    # Search for column names like: nse_symbol, symbol, ticker, code
    for col in df.columns:
        c_clean = str(col).strip().lower().replace("_", "").replace(" ", "")
        if c_clean in ("nsesymbol", "symbol", "ticker", "code"):
            target_col = col
            break
            
    # If no matching column found, check if there's any column containing .NS symbols
    if target_col is None:
        for col in df.columns:
            sample = df[col].dropna().head(5).astype(str)
            if any(s.endswith(".NS") or s.endswith(".BO") for s in sample):
                target_col = col
                break
                
    # If still None, default to the first column
    if target_col is None and len(df.columns) > 0:
        target_col = df.columns[0]
        
    if target_col is not None:
        for val in df[target_col].dropna():
            sym = str(val).strip()
            # Clean Yahoo suffix (.NS or .BO)
            if sym.upper().endswith(".NS"):
                sym = sym[:-3]
            elif sym.upper().endswith(".BO"):
                sym = sym[:-3]
            sym = re.sub(r"[^A-Za-z0-9]", "", sym).upper()
            if sym:
                symbols_set.add(sym)

def extract_symbols_from_files(files_or_paths: list) -> list:
    symbols = set()
    for item in files_or_paths:
        try:
            if isinstance(item, str):
                if item.endswith(".csv"):
                    df = pd.read_csv(item)
                    extract_from_df(df, symbols)
                else:
                    with pd.ExcelFile(item) as xls:
                        for sheet in xls.sheet_names:
                            df = pd.read_excel(xls, sheet_name=sheet)
                            extract_from_df(df, symbols)
            else:
                filename = item.filename
                # Read stream content into ExcelFile or CSV
                if filename.endswith(".csv"):
                    # Rewind file just in case
                    item.file.seek(0)
                    df = pd.read_csv(item.file)
                    extract_from_df(df, symbols)
                else:
                    item.file.seek(0)
                    with pd.ExcelFile(item.file) as xls:
                        for sheet in xls.sheet_names:
                            df = pd.read_excel(xls, sheet_name=sheet)
                            extract_from_df(df, symbols)
        except Exception as e:
            print(f"Error parsing file {item}: {e}")
    return sorted(list(symbols))

def evaluate_retrieved_data(symbol: str, company_name: str, q_financials: list, sector: str, industry: str, peers: list, rules: dict):
    num_quarters = len(q_financials)
    
    min_eps_growth = float(rules.get("min_eps_growth_qoq", 0.0))
    min_sales_growth = float(rules.get("min_sales_growth_qoq", 0.0))
    min_npm_percent = float(rules.get("min_npm_percent", 8.0))
    allow_missing_yoy = rules.get("allow_missing_yoy_for_ipos", True)
    
    quarters_to_check = min(3, num_quarters)
    if quarters_to_check == 0:
        return {
            "symbol": symbol,
            "company_name": company_name,
            "passed": False,
            "metrics": {},
            "reason": "No quarterly data available"
        }
        
    if num_quarters < 4 and not allow_missing_yoy:
        return {
            "symbol": symbol,
            "company_name": company_name,
            "passed": False,
            "metrics": {},
            "reason": f"Insufficient data: only {num_quarters} quarters available, rules require 4 to check 3 QoQ periods."
        }
        
    rejections = []
    metrics_display = {}
    
    # Check last 3 quarters (idx = 0 is latest, idx = 1 is 1 qtr ago, idx = 2 is 2 qtrs ago)
    for idx in range(3):
        q_idx = -1 - idx
        if abs(q_idx) > num_quarters:
            continue
            
        q_data = q_financials[q_idx]
        q_name = q_data.get("quarter", f"Q{q_idx}")
        
        sales = q_data.get("sales")
        npm = q_data.get("npm_percent")
        eps = q_data.get("eps")
        
        # Compare with index q_idx - 1 (the quarter before this one)
        prev_idx = q_idx - 1
        sales_qoq = None
        eps_qoq = None
        
        if abs(prev_idx) <= num_quarters:
            prev_data = q_financials[prev_idx]
            
            prev_sales = prev_data.get("sales")
            if sales is not None and prev_sales is not None and prev_sales > 0:
                sales_qoq = ((sales - prev_sales) / prev_sales) * 100
                
            prev_eps = prev_data.get("eps")
            if eps is not None and prev_eps is not None:
                if prev_eps != 0:
                    eps_qoq = ((eps - prev_eps) / abs(prev_eps)) * 100
                else:
                    eps_qoq = 0.0 if eps == 0 else (100.0 if eps > 0 else -100.0)
                    
        metrics_display[f"Q{idx}_Quarter"] = q_name
        metrics_display[f"Q{idx}_Sales_Cr"] = sales
        metrics_display[f"Q{idx}_Sales_QoQ%"] = round(sales_qoq, 2) if sales_qoq is not None else None
        metrics_display[f"Q{idx}_NPM%"] = npm
        metrics_display[f"Q{idx}_EPS"] = eps
        metrics_display[f"Q{idx}_EPS_QoQ%"] = round(eps_qoq, 2) if eps_qoq is not None else None
        
        # NPM Check
        if npm is None:
            rejections.append(f"{q_name} NPM missing")
        elif npm < min_npm_percent:
            rejections.append(f"{q_name} NPM ({npm:.1f}%) < {min_npm_percent}%")
            
        # Sales growth check
        if sales_qoq is not None and sales_qoq < min_sales_growth:
            rejections.append(f"{q_name} Sales QoQ ({sales_qoq:.1f}%) < {min_sales_growth}%")
        elif sales_qoq is None and abs(prev_idx) <= num_quarters:
            rejections.append(f"{q_name} Sales QoQ missing")
            
        # EPS growth check
        if eps_qoq is not None and eps_qoq < min_eps_growth:
            rejections.append(f"{q_name} EPS QoQ ({eps_qoq:.1f}%) < {min_eps_growth}%")
        elif eps_qoq is None and abs(prev_idx) <= num_quarters:
            rejections.append(f"{q_name} EPS QoQ missing")

    # Resolve Market Cap from peers
    market_cap = None
    for peer in peers:
        if peer.get("symbol", "").upper() == symbol.upper():
            market_cap = peer.get("market_cap_cr")
            break
            
    metrics_display["Market_Cap_Cr"] = market_cap
    metrics_display["Sector"] = sector
    metrics_display["Industry"] = industry

    if rejections:
        return {
            "symbol": symbol,
            "company_name": company_name,
            "passed": False,
            "metrics": metrics_display,
            "reason": ", ".join(rejections)
        }
    else:
        return {
            "symbol": symbol,
            "company_name": company_name,
            "passed": True,
            "metrics": metrics_display,
            "reason": "Passed all QoQ checks"
        }

def evaluate_stock_fundamentals(symbol: str, rules: dict, session=None):
    import time
    import random
    import yfinance as yf
    
    global USE_SCREENER_IN
    
    # 1. First attempt: Scrape Screener.in (if not disabled by a previous timeout in this run)
    if USE_SCREENER_IN:
        # Sleep between 1.0 and 2.0 seconds to distribute requests very gently
        time.sleep(random.uniform(1.0, 2.0))
        try:
            screener_data = scraper.scrape_screener_data(symbol, session=session)
            q_financials = screener_data.get("quarterly_financials", [])
            company_name = screener_data.get("symbol", symbol)
            
            if q_financials:
                # Successfully scraped data from Screener
                return evaluate_retrieved_data(
                    symbol,
                    company_name,
                    q_financials,
                    screener_data.get("sector", "Unknown"),
                    screener_data.get("industry", "Unknown"),
                    screener_data.get("peers", []),
                    rules
                )
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "connection" in err_str or "max retries" in err_str:
                print(f"Screener.in timeout/connection issue for {symbol}. Bypassing Screener.in for the remainder of this run.")
                USE_SCREENER_IN = False
            else:
                print(f"Screener.in fetch failed for {symbol}: {e}. Falling back to Yahoo Finance...")

    # 2. Second attempt: Yahoo Finance (yfinance) Fallback
    try:
        yahoo_symbol = symbol.upper()
        if not yahoo_symbol.endswith(".NS") and not yahoo_symbol.endswith(".BO"):
            yahoo_symbol = f"{yahoo_symbol}.NS"
            
        ticker = yf.Ticker(yahoo_symbol)
        q_fin = ticker.quarterly_financials
        
        # If NSE fails, try BSE (.BO) suffix
        if q_fin.empty:
            yahoo_symbol = f"{symbol.upper()}.BO"
            ticker = yf.Ticker(yahoo_symbol)
            q_fin = ticker.quarterly_financials
            
        if q_fin.empty:
            raise Exception("No quarterly financials found on Yahoo Finance")
            
        info = ticker.info or {}
        company_name = info.get("longName", symbol)
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        market_cap_bytes = info.get("marketCap")
        market_cap_cr = round(market_cap_bytes / 10000000, 1) if market_cap_bytes else None
        
        # Sort dates in chronological ascending order
        dates = sorted(q_fin.columns.tolist())
        
        q_financials = []
        
        revenue_row = q_fin.loc["Total Revenue"] if "Total Revenue" in q_fin.index else None
        net_profit_row = q_fin.loc["Net Income"] if "Net Income" in q_fin.index else None
        eps_row = q_fin.loc["Basic EPS"] if "Basic EPS" in q_fin.index else None
        
        for dt in dates:
            rev_val = float(revenue_row[dt]) if revenue_row is not None and is_not_na(revenue_row[dt]) else None
            np_val = float(net_profit_row[dt]) if net_profit_row is not None and is_not_na(net_profit_row[dt]) else None
            eps_val = float(eps_row[dt]) if eps_row is not None and is_not_na(eps_row[dt]) else None
            
            # Map Yahoo values to standard Crores and decimals
            sales = round(rev_val / 10000000, 2) if rev_val is not None else None
            net_profit = round(np_val / 10000000, 2) if np_val is not None else None
            npm_pct = round((net_profit / sales * 100), 2) if net_profit and sales else None
            q_name = dt.strftime("%b %Y")
            
            q_financials.append({
                "quarter": q_name,
                "sales": sales,
                "net_profit": net_profit,
                "npm_percent": npm_pct,
                "eps": eps_val
            })
            
        peers_mock = [{"symbol": symbol, "market_cap_cr": market_cap_cr}] if market_cap_cr else []
        
        return evaluate_retrieved_data(
            symbol,
            company_name,
            q_financials,
            sector,
            industry,
            peers_mock,
            rules
        )
        
    except Exception as e:
        return {
            "symbol": symbol,
            "company_name": symbol,
            "passed": False,
            "metrics": {},
            "reason": f"Connection timed out (rate-limited by Screener.in) and Yahoo Finance fallback failed: {str(e)}"
        }

@app.get("/api/search")
def search_stock(q: str = Query(..., min_length=1, description="Company name search query")):
    results = scraper.search_company(q)
    return {"results": results}

def get_yahoo_financials_fallback(symbol: str):
    import yfinance as yf
    try:
        yahoo_symbol = symbol.upper()
        if not yahoo_symbol.endswith(".NS") and not yahoo_symbol.endswith(".BO"):
            yahoo_symbol = f"{yahoo_symbol}.NS"
        print(f"   🔎 Fetching Yahoo Finance quarterly financials for {yahoo_symbol}...", flush=True)
        ticker = yf.Ticker(yahoo_symbol)
        q_fin = ticker.quarterly_financials
        if q_fin.empty:
            yahoo_symbol = f"{symbol.upper()}.BO"
            print(f"   🔎 Trying BSE symbol {yahoo_symbol} on Yahoo Finance...", flush=True)
            ticker = yf.Ticker(yahoo_symbol)
            q_fin = ticker.quarterly_financials
        if q_fin.empty:
            print(f"   ⚠️ Yahoo Finance returned empty quarterly financials for {symbol}", flush=True)
            return {"quarterly_financials": [], "sector": "Unknown", "industry": "Unknown", "about": ""}
        
        info = ticker.info or {}
        company_name = info.get("longName", symbol)
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        about = info.get("longBusinessSummary", "")
        
        dates = sorted(q_fin.columns.tolist())
        q_financials = []
        
        revenue_row = q_fin.loc["Total Revenue"] if "Total Revenue" in q_fin.index else None
        net_profit_row = q_fin.loc["Net Income"] if "Net Income" in q_fin.index else None
        eps_row = q_fin.loc["Basic EPS"] if "Basic EPS" in q_fin.index else None
        
        for dt in dates:
            rev_val = float(revenue_row[dt]) if revenue_row is not None and is_not_na(revenue_row[dt]) else None
            np_val = float(net_profit_row[dt]) if net_profit_row is not None and is_not_na(net_profit_row[dt]) else None
            eps_val = float(eps_row[dt]) if eps_row is not None and is_not_na(eps_row[dt]) else None
            
            sales = round(rev_val / 10000000, 2) if rev_val is not None else None
            net_profit = round(np_val / 10000000, 2) if np_val is not None else None
            npm_pct = round((net_profit / sales * 100), 2) if net_profit and sales else None
            q_name = dt.strftime("%b %Y")
            
            q_financials.append({
                "quarter": q_name,
                "sales": sales,
                "net_profit": net_profit,
                "npm_percent": npm_pct,
                "eps": eps_val
            })
            
        print(f"   ✅ Yahoo Finance successfully returned {len(q_financials)} quarters for {symbol}", flush=True)
        return {
            "symbol": company_name,
            "about": about,
            "sector": sector,
            "industry": industry,
            "quarterly_financials": q_financials[-12:],
            "peers": []
        }
    except Exception as e:
        print(f"   ❌ Yahoo Finance fallback error for {symbol}: {e}", flush=True)
        return {"quarterly_financials": [], "sector": "Unknown", "industry": "Unknown", "about": ""}


def run_with_timeout(func, args=(), kwargs={}, timeout=6, default=None):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            print(f"⚠️ {func.__name__} timed out or failed ({e}) after {timeout}s")
            return default

SCREENER_FAIL_COUNT = 0

@app.get("/api/reset-screener")
def reset_screener():
    global USE_SCREENER_IN, SCREENER_FAIL_COUNT
    USE_SCREENER_IN = True
    SCREENER_FAIL_COUNT = 0
    return {"status": "screener_re-enabled"}

@app.get("/api/stock")
def get_stock_data(
    symbol: str = Query(..., description="Screener.in stock symbol/code"),
    x_gemini_api_key: str = Header(None, description="Optional Gemini API key passed from frontend")
):
    clean_sym = symbol.upper().strip()
    cache_file = os.path.join(CACHE_DIR, f"{clean_sym}.json")
    
    # Check disk cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_json = json.load(f)
                if cached_json.get("quarterly_financials") and len(cached_json["quarterly_financials"]) > 0:
                    if not cached_json.get("current_price") or cached_json.get("current_price") == 0:
                        p = get_yahoo_price(clean_sym)
                        if p:
                            cached_json["current_price"] = p
                    print(f"⚡ Loaded {clean_sym} from disk cache", flush=True)
                    return cached_json
        except Exception:
            pass

    global USE_SCREENER_IN, SCREENER_FAIL_COUNT
    screener_data = {}
    
    # 1. Scrape fundamental metrics and peers from Screener.in if not circuit-broken (5s max)
    if USE_SCREENER_IN:
        res = run_with_timeout(scraper.scrape_screener_data, (symbol,), timeout=5, default={})
        if res and res.get("quarterly_financials"):
            screener_data = res
            SCREENER_FAIL_COUNT = 0
        else:
            SCREENER_FAIL_COUNT += 1
            print(f"⚠️ Screener.in failed/rate-limited for {symbol} (Fail count: {SCREENER_FAIL_COUNT})")
            if SCREENER_FAIL_COUNT >= 2:
                print(f"🚨 Screener.in rate-limited repeatedly. Disabling Screener.in for remaining stocks; switching permanently to Yahoo Finance.")
                USE_SCREENER_IN = False
            
    # Fallback to Yahoo Finance if Screener.in disabled or failed (7s max)
    if not screener_data.get("quarterly_financials"):
        print(f"⚡ Using Yahoo Finance fallback for {symbol}...")
        fallback_data = run_with_timeout(get_yahoo_financials_fallback, (symbol,), timeout=7, default={})
        if fallback_data and fallback_data.get("quarterly_financials"):
            screener_data = fallback_data
        else:
            screener_data = {
                "symbol": symbol,
                "about": f"Financial data temporarily unavailable for {symbol}.",
                "sector": "Unknown",
                "industry": "Unknown",
                "quarterly_financials": [],
                "peers": []
            }
            
    # Extract price & fallback if needed
    current_price = screener_data.get("current_price")
    if not current_price:
        current_price = get_yahoo_price(clean_sym)

    result = {
        "symbol": symbol,
        "yahoo_symbol": f"{symbol.upper()}.NS",
        "company_name": screener_data.get("symbol", symbol),
        "about": screener_data.get("about", ""),
        "sector": screener_data.get("sector", "Unknown"),
        "industry": screener_data.get("industry", "Unknown"),
        "current_price": current_price,
        "quarterly_financials": screener_data.get("quarterly_financials", []),
        "peers": screener_data.get("peers", [])
    }
    
    # Save to disk cache if financials were found
    if result.get("quarterly_financials"):
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception:
            pass

    return result




@app.get("/api/config")
def get_config():
    hide_batch = os.getenv("HIDE_BATCH_SCREENER", "true").strip().lower() in ("true", "1", "yes")
    return {
        "hide_batch_screener": hide_batch
    }

@app.get("/api/scanned-files")
def get_scanned_files():
    """List available scan output files in the momentum screener folder."""
    if not os.path.exists(SCREENER_OUTPUTS_DIR):
        return {"files": []}
    files = [f for f in os.listdir(SCREENER_OUTPUTS_DIR) if f.endswith((".xlsx", ".csv"))]
    return {"files": sorted(files, reverse=True)}

@app.get("/api/fundamental-rules")
def get_fundamental_rules():
    return load_rules()

@app.post("/api/fundamental-rules")
def update_fundamental_rules(rules: dict):
    try:
        with open(RULES_FILE, "w") as f:
            json.dump(rules, f, indent=2)
        return {"status": "success", "rules": rules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/batch-screen")
async def run_batch_screen(
    local_files: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None)
):
    global USE_SCREENER_IN
    USE_SCREENER_IN = True
    input_items = []
    
    # Parse local files selection
    if local_files:
        filenames = [f.strip() for f in local_files.split(",") if f.strip()]
        for fn in filenames:
            safe_fn = os.path.basename(fn)
            file_path = os.path.join(SCREENER_OUTPUTS_DIR, safe_fn)
            if os.path.exists(file_path):
                input_items.append(file_path)
                
    if files:
        for f in files:
            input_items.append(f)
            
    if not input_items:
        raise HTTPException(status_code=400, detail="No stock list files uploaded or selected.")
        
    symbols = extract_symbols_from_files(input_items)
    if not symbols:
        raise HTTPException(status_code=400, detail="No stock ticker symbols could be extracted from files.")
        
    rules = load_rules()
    
    # Parallel processing session with tuned connection pool size
    session = requests.Session()
    retries = Retry(total=4, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(pool_connections=15, pool_maxsize=15, max_retries=retries)
    session.mount("https://", adapter)
    
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(evaluate_stock_fundamentals, sym, rules, session): sym for sym in symbols}
        for fut in futures:
            try:
                res = fut.result()
                results.append(res)
            except Exception as e:
                sym = futures[fut]
                results.append({
                    "symbol": sym,
                    "company_name": sym,
                    "passed": False,
                    "metrics": {},
                    "reason": f"System execution error: {str(e)}"
                })
                
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

    # Market view sector metrics
    sector_summary = []
    if passed_rows:
        df_passed = pd.DataFrame(passed_rows, columns=excel_cols)
        summary_df = df_passed.groupby("Sector").agg(
            Count=("Symbol", "count"),
            Avg_Market_Cap_Cr=("Market Cap (Cr)", "mean"),
            Avg_NPM_Q0=("Q0 NPM %", "mean")
        ).reset_index()
        summary_df = summary_df.sort_values("Count", ascending=False).fillna(0.0)
        summary_df["Avg_Market_Cap_Cr"] = summary_df["Avg_Market_Cap_Cr"].round(1)
        summary_df["Avg_NPM_Q0"] = summary_df["Avg_NPM_Q0"].round(2)
        
        sector_summary = summary_df.to_dict(orient="records")
        df_passed_excel = df_passed
    else:
        df_passed_excel = pd.DataFrame(columns=excel_cols)
        summary_df = pd.DataFrame(columns=["Sector", "Count", "Avg_Market_Cap_Cr", "Avg_NPM_Q0"])
        
    df_rejected_excel = pd.DataFrame(rejected_rows, columns=excel_cols)
    
    # Save timestamped files in dd-mm-yyyy_hhmmss format
    now = datetime.datetime.now()
    date_str = now.strftime("%d-%m-%Y")
    time_str = now.strftime("%H%M%S")
    
    strong_filename = f"Strong_Fundamentals_{date_str}_{time_str}.xlsx"
    rejected_filename = f"Rejected_{date_str}_{time_str}.xlsx"
    
    strong_path = os.path.join(OUTPUTS_DIR, strong_filename)
    rejected_path = os.path.join(OUTPUTS_DIR, rejected_filename)
    
    # Write workbooks
    with pd.ExcelWriter(strong_path, engine="openpyxl") as writer:
        df_passed_excel.to_excel(writer, sheet_name="Fundamentals", index=False)
        summary_df.to_excel(writer, sheet_name="Market View", index=False)
        
    with pd.ExcelWriter(rejected_path, engine="openpyxl") as writer:
        df_rejected_excel.to_excel(writer, sheet_name="Rejected", index=False)
        
    return {
        "status": "success",
        "total_checked": len(results),
        "passed_count": len(passed_rows),
        "rejected_count": len(rejected_rows),
        "strong_file": strong_filename,
        "rejected_file": rejected_filename,
        "passed_stocks": passed_rows,
        "rejected_stocks": rejected_rows,
        "sector_summary": sector_summary
    }

@app.get("/api/download")
def download_file(file: str = Query(..., description="Filename to download")):
    safe_name = os.path.basename(file)
    file_path = os.path.join(OUTPUTS_DIR, safe_name)
    if os.path.exists(file_path):
        return FileResponse(
            file_path,
            filename=safe_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    raise HTTPException(status_code=404, detail="Requested spreadsheet output was not found.")

# Mount frontend files at the root if directory exists locally (on Vercel, static assets are served directly via Edge CDN)
if not IS_VERCEL:
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    if os.path.exists(frontend_dir):
        try:
            app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
        except Exception:
            pass
    elif os.path.exists(os.path.join(BASE_DIR, "index.html")):
        try:
            app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
