import os
import sys
import time
import argparse
import subprocess
import urllib.request
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

DEFAULT_APP_URL = "http://127.0.0.1:8000/"

def is_server_running(url=DEFAULT_APP_URL):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False

def ensure_server_running(url=DEFAULT_APP_URL):
    if is_server_running(url):
        print(f"✅ StonksAI server is running at {url}")
        return None
    
    print(f"⚠️ StonksAI server not detected at {url}. Attempting auto-launch...")
    env_python = Path("stocks_env/Scripts/python.exe")
    if not env_python.exists():
        env_python = Path(sys.executable)
    
    proc = subprocess.Popen(
        [str(env_python), "-m", "backend.main"],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to boot up
    for _ in range(15):
        time.sleep(1)
        if is_server_running(url):
            print(f"🚀 StonksAI server started successfully at {url}")
            return proc
    
    print("❌ Failed to start StonksAI server automatically. Please run run_app.bat manually.")
    sys.exit(1)

import re

def parse_input_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")
    
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.xlsx', '.xls']:
        xls = pd.ExcelFile(file_path)
        dfs = [pd.read_excel(xls, sheet_name=s) for s in xls.sheet_names]
    else:
        dfs = [pd.read_csv(file_path)]
    
    stocks = []
    
    for df in dfs:
        target_col = None
        
        # 1. Look for multi-stock list columns ('Stocks Included', 'Stocks', 'Watchlist', etc.)
        multi_stock_cols = ['stocks included', 'stocks', 'watchlist', 'tickers', 'stock_list', 'stocks_included']
        for col in df.columns:
            if str(col).strip().lower() in multi_stock_cols:
                target_col = col
                break

        # 2. Look for single ticker columns ('Symbol', 'Ticker', 'NSE Symbol', 'Code')
        if target_col is None:
            single_cols = ('symbol', 'ticker', 'nsesymbol', 'nsesymbol', 'code', 'stockname', 'company', 'stock')
            for col in df.columns:
                c_clean = str(col).strip().lower().replace("_", "").replace(" ", "")
                if c_clean in single_cols or str(col).strip().lower() in single_cols:
                    target_col = col
                    break

        # 3. Look for column containing .NS or .BO
        if target_col is None:
            for col in df.columns:
                sample = df[col].dropna().head(10).astype(str)
                if any(s.upper().endswith(".NS") or s.upper().endswith(".BO") for s in sample):
                    target_col = col
                    break

        # 4. Fallback to first column
        if target_col is None and len(df.columns) > 0:
            target_col = df.columns[0]

        if target_col is not None:
            raw_cells = df[target_col].dropna().astype(str).tolist()
        else:
            raw_cells = []

        for cell in raw_cells:
            cell_str = str(cell).strip()
            if not cell_str or cell_str.lower() in ['nan', 'none', 'null']:
                continue
            
            items = [x.strip() for x in cell_str.replace('\n', ',').split(',') if x.strip()]
            for item in items:
                sym = item.strip().upper()
                if sym.endswith(".NS"):
                    sym = sym[:-3]
                elif sym.endswith(".BO"):
                    sym = sym[:-3]
                clean_sym = re.sub(r"[^A-Za-z0-9]", "", sym)
                if clean_sym and clean_sym not in stocks and not clean_sym.isdigit() and len(clean_sym) >= 2:
                    stocks.append(clean_sym)

    return stocks




def kill_backend_server():
    try:
        # Get PIDs owning port 8000 using PowerShell (works natively on Windows without psutil)
        cmd = 'powershell -Command "(Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess"'
        output = subprocess.check_output(cmd, shell=True).decode().strip()
        if output:
            pids = set()
            for line in output.split():
                val = line.strip()
                if val.isdigit() and int(val) > 0:
                    pids.add(int(val))
            for pid in pids:
                print(f"   💀 Terminating old backend process PID {pid}...", flush=True)
                subprocess.run(f"taskkill /f /pid {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"   ⚠️ Error terminating old server process: {e}", flush=True)

def restart_backend_server(url=DEFAULT_APP_URL):
    print("🔄 Restarting StonksAI backend server for a fresh network connection...", flush=True)
    kill_backend_server()
    time.sleep(4)
    return ensure_server_running(url)

def capture_stock_screenshots(stocks, app_url, output_dir, headless=True):
    from playwright.sync_api import sync_playwright
    
    os.makedirs(output_dir, exist_ok=True)
    screenshot_results = {}
    
    BATCH_SIZE = 40
    COOLDOWN_SECONDS = 30

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        page.set_default_timeout(200000)
        
        print(f"🌐 Opening {app_url} in Playwright...", flush=True)
        page.goto(app_url, wait_until="networkidle")

        start_time_all = time.time()
        for idx, stock in enumerate(stocks, 1):
            full_path = os.path.join(output_dir, f"{stock}_full.png")
            
            # Resume check: if screenshot already captured on disk, skip network call!
            if os.path.exists(full_path) and os.path.getsize(full_path) > 1000:
                print(f"   ⏩ Already captured screenshot for {stock}, skipping...", flush=True)
                screenshot_results[stock] = {
                    "symbol": stock,
                    "company_name": stock,
                    "sector": "N/A",
                    "industry": "N/A",
                    "full_img": full_path,
                    "status": "success"
                }
                continue

            # Batch reconnect check every 40 stocks: close browser & restart server for fresh IP session
            if idx > 1 and (idx - 1) % BATCH_SIZE == 0:
                print(f"\n🔄 Processed batch of {idx - 1} stocks. Recycling backend server & browser connection...", flush=True)
                try:
                    page.close()
                    browser.close()
                except Exception:
                    pass
                
                restart_backend_server(app_url)
                time.sleep(COOLDOWN_SECONDS)
                
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context(viewport={"width": 1400, "height": 900})
                page = context.new_page()
                page.set_default_timeout(200000)
                page.goto(app_url, wait_until="networkidle")
                print(f"🚀 Fresh session established. Resuming stock analysis...", flush=True)

            pct = int((idx / len(stocks)) * 100)
            elapsed_total = time.time() - start_time_all
            avg_per_stock = elapsed_total / (idx - 1) if idx > 1 else 2.5
            remaining_sec = int(avg_per_stock * (len(stocks) - idx + 1))
            rem_m, rem_s = divmod(remaining_sec, 60)
            eta_str = f"{rem_m}m {rem_s}s" if rem_m > 0 else f"{rem_s}s"
            
            print(f"\n⏳ [{idx}/{len(stocks)}] ({pct}%) Analyzing stock: {stock} ... [ETA: ~{eta_str}]", flush=True)
            time.sleep(0.5)

            try:
                api_url = f"{app_url.rstrip('/')}/api/stock?symbol={stock}"
                
                # First attempt
                try:
                    api_resp = requests.get(api_url, timeout=(5, 55))
                except requests.exceptions.Timeout:
                    print(f"   ⚠️ Initial request timed out for {stock}, retrying after 5s...", flush=True)
                    time.sleep(5)
                    api_resp = requests.get(api_url, timeout=(5, 55))

                if api_resp.status_code != 200:
                    raise Exception(f"API returned HTTP {api_resp.status_code}")
                
                data = api_resp.json()
                if data.get("error") and not data.get("quarterly_financials"):
                    raise Exception(data.get("error", "Unknown API error"))
                
                page.evaluate("""(data) => {
                    document.getElementById('welcome-view').classList.add('hidden');
                    document.getElementById('loading-view').classList.add('hidden');
                    document.getElementById('error-view').classList.add('hidden');
                    if (document.getElementById('batch-results-view'))
                        document.getElementById('batch-results-view').classList.add('hidden');
                    populateDashboard(data);
                    document.getElementById('dashboard-view').classList.remove('hidden');
                }""", data)
                time.sleep(1.2)
                
                try:
                    comp_name = page.inner_text("#stock-name").strip()
                except Exception:
                    comp_name = data.get("company_name", stock)
                    
                try:
                    sector = page.inner_text("#stock-sector").strip()
                except Exception:
                    sector = data.get("sector", "N/A")
                    
                try:
                    industry = page.inner_text("#stock-industry").strip()
                except Exception:
                    industry = data.get("industry", "N/A")

                # Full Dashboard Screenshot (#dashboard-view)
                if page.is_visible("#dashboard-view"):
                    dash_elem = page.query_selector("#dashboard-view")
                    if dash_elem:
                        dash_elem.screenshot(path=full_path, timeout=10000)
                        print(f"   📸 Screenshot saved for {stock} ({comp_name})", flush=True)
                    else:
                        full_path = None
                else:
                    full_path = None
                    print(f"   ⚠️ Dashboard view not visible for {stock}", flush=True)
                    
                screenshot_results[stock] = {
                    "symbol": stock,
                    "company_name": comp_name,
                    "sector": sector,
                    "industry": industry,
                    "full_img": full_path,
                    "status": "success" if full_path else "Data Unavailable"
                }

            except requests.exceptions.Timeout:
                print(f"   ⏰ Backend timed out twice for {stock} (60s), skipping...", flush=True)
                screenshot_results[stock] = {
                    "symbol": stock,
                    "company_name": stock,
                    "sector": "N/A",
                    "industry": "N/A",
                    "full_img": None,
                    "status": "timeout"
                }

            except Exception as err:
                print(f"   ❌ Error loading data for {stock}: {err}", flush=True)
                screenshot_results[stock] = {
                    "symbol": stock,
                    "company_name": stock,
                    "sector": "N/A",
                    "industry": "N/A",
                    "full_img": None,
                    "status": f"error: {err}"
                }

        try:
            browser.close()
        except Exception:
            pass
    
    return screenshot_results


def create_docx_report(results, output_docx_path):
    doc = Document()
    
    # Set narrow 0.4 inch margins for maximum printable area
    for section in doc.sections:
        section.top_margin = Inches(0.4)
        section.bottom_margin = Inches(0.4)
        section.left_margin = Inches(0.4)
        section.right_margin = Inches(0.4)
        section.header_distance = Inches(0.2)
        section.footer_distance = Inches(0.2)

    for idx, (symbol, data) in enumerate(results.items()):
        if idx > 0:
            doc.add_page_break()
            
        # Compact single-page Stock Header
        header_p = doc.add_paragraph()
        header_p.paragraph_format.space_before = Pt(0)
        header_p.paragraph_format.space_after = Pt(4)
        header_p.paragraph_format.line_spacing = 1.0
        
        run_idx = header_p.add_run(f"{idx+1}. {data['company_name']} ({data['symbol']})  ")
        run_idx.font.name = "Calibri"
        run_idx.font.size = Pt(14)
        run_idx.font.bold = True
        run_idx.font.color.rgb = RGBColor(30, 41, 59)
        
        run_meta = header_p.add_run(f"|  Sector: {data['sector']}  |  Industry: {data['industry']}")
        run_meta.font.name = "Calibri"
        run_meta.font.size = Pt(10)
        run_meta.font.bold = True
        run_meta.font.color.rgb = RGBColor(99, 102, 241)
        
        if data["status"] != "success":
            err_p = doc.add_paragraph()
            err_run = err_p.add_run(f"⚠️ Failed to fetch details for {symbol}. Error: {data['status']}")
            err_run.font.color.rgb = RGBColor(239, 68, 68)
            continue
            
        # Full Dashboard Screenshot (Constrained height to guarantee 1 single page fit)
        if data["full_img"] and os.path.exists(data["full_img"]):
            p_img = doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.paragraph_format.space_before = Pt(2)
            p_img.paragraph_format.space_after = Pt(0)
            p_img.paragraph_format.line_spacing = 1.0
            
            # Constrain height to 9.4 inches so title + image fit on EXACTLY 1 page
            p_img.add_run().add_picture(data["full_img"], height=Inches(9.4))
            
    doc.save(output_docx_path)
    print(f"\n🎉 Successfully saved report (1 page per stock) to: {output_docx_path}")


def find_default_input_file():
    search_dirs = [
        os.path.join("momentum_screener", "outputs"),
        "outputs",
        "."
    ]
    # Priority 1: filtered_stocks_*.xlsx or filtered_stocks_*.csv
    for d in search_dirs:
        if os.path.exists(d):
            files = [os.path.join(d, f) for f in os.listdir(d) if f.startswith("filtered_stocks_") and f.endswith(('.xlsx', '.csv')) and not f.startswith("~$")]
            if files:
                files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                return files[0]
                
    # Priority 2: easy_scans_watchlist_*.xlsx or any recent excel/csv
    for d in search_dirs:
        if os.path.exists(d):
            files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(('.xlsx', '.csv')) and not f.startswith("~$")]
            if files:
                files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                return files[0]
                
    return "sample_stocks.csv"

def get_default_output_path():
    out_dir = "outputs"
    os.makedirs(out_dir, exist_ok=True)
    today_str = datetime.now().strftime("%d-%m-%Y")
    return os.path.join(out_dir, f"filtered_stocks_report_{today_str}.docx")

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
        
    default_input = find_default_input_file()
    default_output = get_default_output_path()

    parser = argparse.ArgumentParser(description="Generate Word (.docx) Fundamental Analysis Report from CSV/Excel using StonksAI local web app.")

    parser.add_argument("--input", "-i", default=default_input, help="Path to input CSV or Excel file containing stock symbols")
    parser.add_argument("--output", "-o", default=default_output, help="Path to output .docx file")
    parser.add_argument("--max-stocks", "-m", type=int, default=0, help="Maximum number of stocks to process (0 = process all)")
    parser.add_argument("--url", "-u", default=DEFAULT_APP_URL, help="URL of running StonksAI web app")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed (visible) mode for debugging")
    
    args = parser.parse_args()
    
    # Ensure output directory exists if custom path provided
    out_parent = os.path.dirname(args.output)
    if out_parent:
        os.makedirs(out_parent, exist_ok=True)

    server_proc = ensure_server_running(args.url)
    
    try:
        stocks = parse_input_file(args.input)
        total_found = len(stocks)
        if args.max_stocks > 0 and len(stocks) > args.max_stocks:
            stocks = stocks[:args.max_stocks]
            print(f"📋 Loaded {total_found} stock symbols from {args.input} (processing top {len(stocks)}): {', '.join(stocks[:10])}...")
        else:
            print(f"📋 Loaded {len(stocks)} stock symbols from {args.input}: {', '.join(stocks[:10])}{'...' if len(stocks) > 10 else ''}")
    except Exception as e:
        print(f"❌ Error reading input file: {e}")
        sys.exit(1)

        
    if not stocks:
        print("❌ No stock symbols found in input file.")
        sys.exit(1)
        
    temp_dir = os.path.join("outputs", "temp_screenshots")
    screenshot_data = capture_stock_screenshots(stocks, args.url, temp_dir, headless=not args.headed)
    
    create_docx_report(screenshot_data, args.output)

if __name__ == "__main__":
    main()

