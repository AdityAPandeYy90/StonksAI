import urllib.request
import json
import csv
import io
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# Configuration
UNIVERSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MIN_PRICE = 50.0
MIN_VOLUME_AVG = 100000
NUM_THREADS = 50
DCR_DAYS = 10

def fetch_all_nse_tickers():
    print("Fetching entire listed equity list from NSE...")
    try:
        req = urllib.request.Request(UNIVERSE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
        
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        
        header_lower = [h.strip().lower() for h in header]
        symbol_idx = header_lower.index("symbol")
        series_idx = header_lower.index("series") if "series" in header_lower else -1
        
        tickers = []
        for row in reader:
            if row and len(row) > symbol_idx:
                symbol = row[symbol_idx].strip()
                if series_idx != -1 and len(row) > series_idx:
                    series = row[series_idx].strip().upper()
                    if series != "EQ":
                        continue
                if symbol:
                    tickers.append(f"{symbol}.NS")
        print(f"Loaded {len(tickers)} active EQ tickers from NSE successfully.")
        return tickers
    except Exception as e:
        print(f"Error fetching ticker list: {e}")
        sys.exit(1)

def fetch_stock_data(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=6mo&interval=1d"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
        
        chart_result = res_data.get('chart', {}).get('result', [])
        if not chart_result:
            return ticker, None
            
        result = chart_result[0]
        timestamps = result.get('timestamp', [])
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        close_prices = quote.get('close', [])
        volumes = quote.get('volume', [])
        
        clean_data = []
        for i, (t, c, v) in enumerate(zip(timestamps, close_prices, volumes)):
            if t is not None:
                # Handle Yahoo Finance lag where the latest daily close is None but stored in regularMarketPrice
                if c is None and i == len(close_prices) - 1:
                    c = result.get('meta', {}).get('regularMarketPrice')
                if c is not None and v is not None:
                    clean_data.append({
                        'date': datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d'),
                        'close': float(c),
                        'volume': int(v)
                    })
        return ticker, clean_data
    except Exception:
        return ticker, None

def generate_styled_excel(daily_stats, filename):
    print(f"Generating styled Excel file: {filename}...")
    
    # SpreadsheetML XML template
    xml_header = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
 <DocumentProperties xmlns="urn:schemas-microsoft-com:office:office">
  <Author>Stockbee Market Monitor</Author>
  <Created>2026-07-30T12:00:00Z</Created>
 </DocumentProperties>
 <Styles>
  <Style ss:ID="Default" ss:Name="Normal">
   <Alignment ss:Vertical="Bottom"/>
   <Borders/>
   <Font ss:FontName="Calibri" x:Family="Swiss" ss:Size="11" ss:Color="#000000"/>
   <Interior/>
   <NumberFormat/>
   <Protection/>
  </Style>
  <Style ss:ID="HeaderTitle">
   <Font ss:FontName="Calibri" ss:Size="16" ss:Bold="1" ss:Color="#1F4E78"/>
   <Alignment ss:Horizontal="Left" ss:Vertical="Center"/>
  </Style>
  <Style ss:ID="PrimaryHeader">
   <Font ss:FontName="Calibri" ss:Bold="1" ss:Color="#000000"/>
   <Interior ss:Color="#00FFFF" ss:Pattern="Solid"/>
   <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1"/>
   </Borders>
  </Style>
  <Style ss:ID="SecondaryHeader">
   <Font ss:FontName="Calibri" ss:Bold="1" ss:Color="#000000"/>
   <Interior ss:Color="#FFFF00" ss:Pattern="Solid"/>
   <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1"/>
   </Borders>
  </Style>
  <Style ss:ID="GeneralHeader">
   <Font ss:FontName="Calibri" ss:Bold="1" ss:Color="#000000"/>
   <Interior ss:Color="#F2F2F2" ss:Pattern="Solid"/>
   <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1"/>
   </Borders>
  </Style>
  <Style ss:ID="GreenCell">
   <Interior ss:Color="#C6EFCE" ss:Pattern="Solid"/>
   <Font ss:Color="#006100" ss:Bold="1"/>
   <Alignment ss:Horizontal="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
  <Style ss:ID="RedCell">
   <Interior ss:Color="#FFC7CE" ss:Pattern="Solid"/>
   <Font ss:Color="#9C0006" ss:Bold="1"/>
   <Alignment ss:Horizontal="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
  <Style ss:ID="PinkCell">
   <Interior ss:Color="#FFC7CE" ss:Pattern="Solid"/>
   <Font ss:Color="#9C0006"/>
   <Alignment ss:Horizontal="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
  <Style ss:ID="DarkRedCell">
   <Interior ss:Color="#FFC7CE" ss:Pattern="Solid"/>
   <Font ss:Color="#9C0006"/>
   <Alignment ss:Horizontal="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
  <Style ss:ID="NormalCell">
   <Alignment ss:Horizontal="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
  <Style ss:ID="DateCell">
   <Alignment ss:Horizontal="Center"/>
   <NumberFormat ss:Format="Short Date"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
  <Style ss:ID="DecimalCell">
   <Alignment ss:Horizontal="Center"/>
   <NumberFormat ss:Format="0.00"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9D9D9"/>
   </Borders>
  </Style>
 </Styles>
 <Worksheet ss:Name="Market Monitor">
  <Table x:FullColumns="1" x:FullRows="1" ss:DefaultColumnWidth="80">
   <Column ss:Width="90"/>
   <Column ss:Width="90"/>
   <Column ss:Width="90"/>
   <Column ss:Width="70"/>
   <Column ss:Width="70"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Column ss:Width="90"/>
   <Column ss:Width="70"/>
   <Column ss:Width="90"/>
   <Row ss:Height="25">
    <Cell ss:MergeAcross="16" ss:StyleID="HeaderTitle"><Data ss:Type="String">Stockbee Market Monitor 2026 (NSE India)</Data></Cell>
   </Row>
   <Row ss:Height="25">
    <Cell ss:Index="2" ss:MergeAcross="5" ss:StyleID="PrimaryHeader"><Data ss:Type="String">Primary Breadth Indicators</Data></Cell>
    <Cell ss:Index="8" ss:MergeAcross="6" ss:StyleID="SecondaryHeader"><Data ss:Type="String">Secondary Breadth Indicators</Data></Cell>
   </Row>
   <Row ss:Height="40">
    <Cell ss:StyleID="GeneralHeader"><Data ss:Type="String">Date</Data></Cell>
    <Cell ss:StyleID="PrimaryHeader"><Data ss:Type="String">Number of stocks up 4% plus today</Data></Cell>
    <Cell ss:StyleID="PrimaryHeader"><Data ss:Type="String">Number of stocks down 4% plus today</Data></Cell>
    <Cell ss:StyleID="PrimaryHeader"><Data ss:Type="String">5 day ratio</Data></Cell>
    <Cell ss:StyleID="PrimaryHeader"><Data ss:Type="String">10 day ratio</Data></Cell>
    <Cell ss:StyleID="PrimaryHeader"><Data ss:Type="String">Number of stocks up 25% plus in a quarter</Data></Cell>
    <Cell ss:StyleID="PrimaryHeader"><Data ss:Type="String">Number of stocks down 25% + in a quarter</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">Number of stocks up 25% + in a month</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">Number of stocks down 25% + in a month</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">Number of stocks up 50% + in a month</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">Number of stocks down 50% + in a month</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">Number of stocks up 13% + in 34 days</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">Number of stocks down 13% + in 34 days</Data></Cell>
    <Cell ss:StyleID="SecondaryHeader"><Data ss:Type="String">% of stocks up 13% + in 34 days</Data></Cell>
    <Cell ss:StyleID="GeneralHeader"><Data ss:Type="String">NSE Common stock universe</Data></Cell>
    <Cell ss:StyleID="GeneralHeader"><Data ss:Type="String">T2108 (Above 40 SMA)</Data></Cell>
    <Cell ss:StyleID="GeneralHeader"><Data ss:Type="String">Nifty Close</Data></Cell>
   </Row>
"""

    xml_body = ""
    # Write rows in reverse chronological order (newest first) just like the screenshot
    for stats in reversed(daily_stats):
        # Determine Styles based on Bullish vs Bearish values
        # Group 1: 4% plus vs 4% minus
        plus_4_style = "GreenCell" if stats['4%_plus'] >= stats['4%_minus'] else "DarkRedCell"
        minus_4_style = "GreenCell" if stats['4%_plus'] >= stats['4%_minus'] else "PinkCell"
        
        # Group 2: 25% plus quarter vs 25% minus quarter
        plus_25q_style = "GreenCell" if stats['25%_plus_3m'] >= stats['25%_minus_3m'] else "DarkRedCell"
        minus_25q_style = "GreenCell" if stats['25%_plus_3m'] >= stats['25%_minus_3m'] else "PinkCell"
        
        # Group 3: 25% plus month vs 25% minus month
        plus_25m_style = "GreenCell" if stats['25%_plus_1m'] >= stats['25%_minus_1m'] else "DarkRedCell"
        minus_25m_style = "GreenCell" if stats['25%_plus_1m'] >= stats['25%_minus_1m'] else "PinkCell"

        # Group 4: 13% plus 34d vs 13% minus 34d
        plus_13_style = "GreenCell" if stats['13%_plus'] >= stats['13%_minus'] else "DarkRedCell"
        minus_13_style = "GreenCell" if stats['13%_plus'] >= stats['13%_minus'] else "PinkCell"

        dcr_5 = stats.get('dcr_5', 1.0)
        dcr_10 = stats.get('dcr', 1.0)
        t2108 = stats.get('t2108', 0.0)
        nifty = stats.get('nifty_close', 0.0)
        pct_13_34d = stats.get('pct_13_34d', 0.0)

        xml_body += f"""   <Row ss:Height="20">
    <Cell ss:StyleID="DateCell"><Data ss:Type="String">{stats['date']}</Data></Cell>
    <Cell ss:StyleID="{plus_4_style}"><Data ss:Type="Number">{stats['4%_plus']}</Data></Cell>
    <Cell ss:StyleID="{minus_4_style}"><Data ss:Type="Number">{stats['4%_minus']}</Data></Cell>
    <Cell ss:StyleID="DecimalCell"><Data ss:Type="Number">{dcr_5:.2f}</Data></Cell>
    <Cell ss:StyleID="DecimalCell"><Data ss:Type="Number">{dcr_10:.2f}</Data></Cell>
    <Cell ss:StyleID="{plus_25q_style}"><Data ss:Type="Number">{stats['25%_plus_3m']}</Data></Cell>
    <Cell ss:StyleID="{minus_25q_style}"><Data ss:Type="Number">{stats['25%_minus_3m']}</Data></Cell>
    <Cell ss:StyleID="{plus_25m_style}"><Data ss:Type="Number">{stats['25%_plus_1m']}</Data></Cell>
    <Cell ss:StyleID="{minus_25m_style}"><Data ss:Type="Number">{stats['25%_minus_1m']}</Data></Cell>
    <Cell ss:StyleID="NormalCell"><Data ss:Type="Number">{stats['50%_plus_1m']}</Data></Cell>
    <Cell ss:StyleID="GreenCell"><Data ss:Type="Number">{stats['50%_minus_1m']}</Data></Cell>
    <Cell ss:StyleID="{plus_13_style}"><Data ss:Type="Number">{stats['13%_plus']}</Data></Cell>
    <Cell ss:StyleID="{minus_13_style}"><Data ss:Type="Number">{stats['13%_minus']}</Data></Cell>
    <Cell ss:StyleID="DecimalCell"><Data ss:Type="Number">{pct_13_34d:.2f}</Data></Cell>
    <Cell ss:StyleID="NormalCell"><Data ss:Type="Number">{stats['eligible_universe']}</Data></Cell>
    <Cell ss:StyleID="DecimalCell"><Data ss:Type="Number">{t2108:.2f}</Data></Cell>
    <Cell ss:StyleID="DecimalCell"><Data ss:Type="Number">{nifty:.2f}</Data></Cell>
   </Row>
"""

    xml_footer = """  </Table>
  <WorksheetOptions xmlns="urn:schemas-microsoft-com:office:excel">
   <Selected/>
   <ProtectObjects>False</ProtectObjects>
   <ProtectScenarios>False</ProtectScenarios>
  </WorksheetOptions>
 </Worksheet>
</Workbook>
"""

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(xml_header + xml_body + xml_footer)
        print(f"Excel monitor created successfully: {filename}")
    except PermissionError:
        print(f"WARNING: Could not write to {filename} because it is currently open in Excel. Please close it.")

def process_market_breadth(ticker_data_map):
    print("\nProcessing whole exchange breadth metrics...")
    
    baseline_dates = []
    # Find the ticker with the maximum number of data points to ensure we get the latest trading day
    best_ticker = max(ticker_data_map.keys(), key=lambda k: len(ticker_data_map[k]) if ticker_data_map[k] else 0)
    if best_ticker and ticker_data_map[best_ticker]:
        baseline_dates = [d['date'] for d in ticker_data_map[best_ticker]]

            
    if not baseline_dates:
        print("Error: Could not establish trading dates baseline.")
        return
        
    baseline_dates = sorted(list(set(baseline_dates)))
    total_days = len(baseline_dates)
    print(f"Trading days identified in data: {total_days}")
    
    if total_days < DCR_DAYS + 2:
        print("Error: Insufficient historical data points.")
        return
        
    date_to_idx = {date: idx for idx, date in enumerate(baseline_dates)}
    
    ticker_history = {}
    for ticker, data in ticker_data_map.items():
        if not data:
            continue
        history = {}
        for item in data:
            d = item['date']
            if d in date_to_idx:
                history[date_to_idx[d]] = item
        ticker_history[ticker] = history

    # We evaluate for the last 30 days to build a rich historical excel workbook
    table_days = 30
    days_to_evaluate = list(range(total_days - table_days, total_days))
    
    daily_stats = []
    today_breakouts = []
    today_breakdowns = []
    
    for idx in days_to_evaluate:
        date_str = baseline_dates[idx]
        
        count_4_plus = 0
        count_4_minus = 0
        count_13_plus = 0
        count_13_minus = 0
        count_25_plus_1m = 0
        count_25_minus_1m = 0
        count_25_plus_3m = 0
        count_25_minus_3m = 0
        count_50_plus_1m = 0
        count_50_minus_1m = 0
        total_eligible = 0
        stocks_above_40sma = 0
        
        for ticker, history in ticker_history.items():
            if ticker == "^NSEI":
                continue
            if idx not in history or (idx - 1) not in history:
                continue
                
            curr = history[idx]
            prev = history[idx - 1]
            
            # 20-day average volume lookup
            vol_sum = 0
            vol_count = 0
            for v_idx in range(max(0, idx - 19), idx + 1):
                if v_idx in history:
                    vol_sum += history[v_idx]['volume']
                    vol_count += 1
            avg_vol = vol_sum / vol_count if vol_count > 0 else 0
            
            # Universe Liquidity Filters
            if curr['close'] < MIN_PRICE or avg_vol < MIN_VOLUME_AVG:
                continue
                
            total_eligible += 1
            
            # T2108 (Above 40 SMA) Calculation
            sma_40_sum = 0
            sma_40_count = 0
            for s_idx in range(max(0, idx - 39), idx + 1):
                if s_idx in history:
                    sma_40_sum += history[s_idx]['close']
                    sma_40_count += 1
            sma_40 = sma_40_sum / sma_40_count if sma_40_count > 0 else 0
            if curr['close'] > sma_40:
                stocks_above_40sma += 1
            
            # 1-day change
            change_1d = curr['close'] / prev['close']
            is_4_plus = change_1d >= 1.04
            is_4_minus = change_1d <= 0.96
            
            if is_4_plus:
                count_4_plus += 1
                if idx == total_days - 1:
                    today_breakouts.append((ticker, curr['close'], (change_1d - 1)*100, curr['volume']))
            elif is_4_minus:
                count_4_minus += 1
                if idx == total_days - 1:
                    today_breakdowns.append((ticker, curr['close'], (change_1d - 1)*100, curr['volume']))
                    
            # 34-day change
            if (idx - 34) in history:
                change_34d = curr['close'] / history[idx - 34]['close']
                if change_34d >= 1.13:
                    count_13_plus += 1
                elif change_34d <= 0.87:
                    count_13_minus += 1
                    
            # 21-day change (1 month)
            if (idx - 21) in history:
                change_21d = curr['close'] / history[idx - 21]['close']
                if change_21d >= 1.25:
                    count_25_plus_1m += 1
                elif change_21d <= 0.75:
                    count_25_minus_1m += 1
                    
                if change_21d >= 1.50:
                    count_50_plus_1m += 1
                elif change_21d <= 0.50:
                    count_50_minus_1m += 1
                    
            # 65-day change (1 quarter)
            if (idx - 65) in history:
                change_65d = curr['close'] / history[idx - 65]['close']
                if change_65d >= 1.25:
                    count_25_plus_3m += 1
                elif change_65d <= 0.75:
                    count_25_minus_3m += 1
                    
        # Nifty Index Value
        nifty_val = 0.0
        if "^NSEI" in ticker_history and idx in ticker_history["^NSEI"]:
            nifty_val = ticker_history["^NSEI"][idx]['close']
            
        daily_stats.append({
            'date': date_str,
            'eligible_universe': total_eligible,
            '4%_plus': count_4_plus,
            '4%_minus': count_4_minus,
            '13%_plus': count_13_plus,
            '13%_minus': count_13_minus,
            'pct_13_34d': (count_13_plus / total_eligible * 100) if total_eligible > 0 else 0,
            '25%_plus_1m': count_25_plus_1m,
            '25%_minus_1m': count_25_minus_1m,
            '25%_plus_3m': count_25_plus_3m,
            '25%_minus_3m': count_25_minus_3m,
            '50%_plus_1m': count_50_plus_1m,
            '50%_minus_1m': count_50_minus_1m,
            't2108': (stocks_above_40sma / total_eligible * 100) if total_eligible > 0 else 0,
            'nifty_close': nifty_val
        })

    # Compute 5-day and 10-day DCR for each day in our table
    for stats in daily_stats:
        baseline_idx = date_to_idx[stats['date']]
        
        # 10D DCR
        sum_10_plus = 0
        sum_10_minus = 0
        # 5D DCR
        sum_5_plus = 0
        sum_5_minus = 0
        
        for offset in range(DCR_DAYS):
            d_idx = baseline_idx - offset
            c_plus = 0
            c_minus = 0
            for ticker, history in ticker_history.items():
                if ticker == "^NSEI":
                    continue
                if d_idx in history and (d_idx - 1) in history:
                    curr = history[d_idx]
                    prev = history[d_idx - 1]
                    
                    vol_sum = 0
                    vol_count = 0
                    for v_idx in range(max(0, d_idx - 19), d_idx + 1):
                        if v_idx in history:
                            vol_sum += history[v_idx]['volume']
                            vol_count += 1
                    avg_vol = vol_sum / vol_count if vol_count > 0 else 0
                    
                    if curr['close'] >= MIN_PRICE and avg_vol >= MIN_VOLUME_AVG:
                        change_1d = curr['close'] / prev['close']
                        if change_1d >= 1.04:
                            c_plus += 1
                        elif change_1d <= 0.96:
                            c_minus += 1
            
            # Accumulate 10D
            sum_10_plus += c_plus
            sum_10_minus += c_minus
            # Accumulate 5D
            if offset < 5:
                sum_5_plus += c_plus
                sum_5_minus += c_minus
            
        stats['dcr'] = sum_10_plus / sum_10_minus if sum_10_minus > 0 else sum_10_plus
        stats['dcr_5'] = sum_5_plus / sum_5_minus if sum_5_minus > 0 else sum_5_plus

    # Print Table
    print("\n" + "="*95)
    print("                    STOCKBEE MARKET MONITOR (INDIAN NSE WHOLE EXCHANGE)                   ")
    print("="*95)
    print(f"{'Date':12} | {'Univ':4} | {'4% +':5} | {'4% -':5} | {'13% +':5} | {'13% -':5} | {'25%+ 1M':7} | {'25%- 1M':7} | {'50%+ 1M':7} | {'10D DCR':7}")
    print("-"*95)
    # Print the last 12 days in the console for readability
    for stats in daily_stats[-12:]:
        dcr_str = f"{stats['dcr']:.2f}" if 'dcr' in stats else "N/A"
        print(f"{stats['date']:12} | {stats['eligible_universe']:4d} | {stats['4%_plus']:5d} | {stats['4%_minus']:5d} | {stats['13%_plus']:5d} | {stats['13%_minus']:5d} | {stats['25%_plus_1m']:7d} | {stats['25%_minus_1m']:7d} | {stats['50%_plus_1m']:7d} | {dcr_str:7}")
    print("="*95)
    
    # Current Regime assessment & Action Plan
    latest = daily_stats[-1]
    latest_dcr = latest.get('dcr', 1.0)
    
    print("\n" + "="*65)
    print("           STOCKBEE ACTION PLAN & TL;DR FOR TOMORROW           ")
    print("="*65)
    print(f"Current 10-Day Ratio (DCR): {latest_dcr:.2f}")
    
    if latest_dcr > 2.0:
        print("POSTURE          : GREEN LIGHT - RISK-ON (TAILWIND)")
        print("POSITION SIZING  : Full position sizes (e.g. 10% risk per trade) authorized.")
        print("EXPECTED HOLD    : Trend trade. Hold breakouts for large moves (20%-40%+).")
    elif latest_dcr < 0.5:
        print("POSTURE          : RED LIGHT - RISK-OFF (HEADWIND)")
        print("POSITION SIZING  : 0% Sizing (NO NEW LONGS). Sit in cash.")
        print("EXPECTED HOLD    : Manage trailing stops on existing open positions.")
    else:
        print("POSTURE          : YELLOW LIGHT - NEUTRAL (CROSSWIND) - CAUTIOUS")
        print("POSITION SIZING  : Halve position sizes (e.g. 5% risk max per trade).")
        print("EXPECTED HOLD    : Swing trade. Take quick profits (10%-15% targets) into strength.")
        
    print("-"*65)
    print("WARNING FLAGS / ALERTS:")
    
    # Overheating Check (Whole Exchange scale: >= 15 stocks)
    overheat_count = latest['50%_plus_1m']
    overheat_alert = "!! DANGER: Overheated !!" if overheat_count >= 15 else "OK (Normal)"
    print(f"  * Overheating Alert (50%+ in 1M)  : {overheat_count} stocks (Threshold: >=15) -> {overheat_alert}")
    if overheat_count >= 15:
        print("    [ALERT] Market is hyper-extended. Do NOT buy breakouts. Tighten stops and raise cash.")
        
    # Capitulation Check (Whole Exchange scale: >= 300 stocks)
    capit_count = latest['4%_minus']
    capit_alert = "!! PANIC DETECTED (Capitulation) !!" if capit_count >= 300 else "OK (Normal)"
    print(f"  * Capitulation Alert (4%- Today) : {capit_count} stocks (Threshold: >=300) -> {capit_alert}")
    if capit_count >= 300:
        print("    [ALERT] Heavy selling. Watch for counts to dry up to signal a potential market bottom.")
    print("="*65)


    # Save to CSV log
    csv_file = "market_monitor_all_nse_history.csv"
    file_exists = False
    is_duplicate = False
    try:
        with open(csv_file, 'r', newline='') as f:
            file_exists = True
            reader = list(csv.reader(f))
            if len(reader) > 1:
                last_row = reader[-1]
                if last_row[0] == latest['date']:
                    is_duplicate = True
    except FileNotFoundError:
        pass
    except Exception:
        file_exists = True
        
    if is_duplicate:
        print(f"\nData for {latest['date']} is already logged in {csv_file}. Skipping append to prevent duplicate rows.")
    else:
        try:
            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Date', 'Universe', '4% Plus', '4% Minus', '13% Plus', '13% Minus', '13% Plus 34D Pct', '25% Plus 1M', '25% Minus 1M', '50% Plus 1M', '10D DCR'])
                writer.writerow([
                    latest['date'], latest['eligible_universe'], latest['4%_plus'], latest['4%_minus'],
                    latest['13%_plus'], latest['13%_minus'], f"{latest['pct_13_34d']:.2f}", latest['25%_plus_1m'], latest['25%_minus_1m'],
                    latest['50%_plus_1m'], f"{latest_dcr:.2f}"
                ])
            print(f"\nSaved today's data to log: {csv_file}")
        except PermissionError:
            print(f"\nWARNING: Could not write to {csv_file} because it is currently open in another program.")


    # Generate styled Excel sheets
    generate_styled_excel(daily_stats, "market_monitor_all_nse_sheet.xls")

    # Today's Breakouts printout
    print("\n--- TODAY'S 4% BREAKOUTS (NSE ALL COMMON) ---")
    sorted_breakouts = sorted(today_breakouts, key=lambda x: x[2], reverse=True)
    if sorted_breakouts:
        print(f"{'Ticker':12} | {'Close':8} | {'% Change':8} | {'Volume':10}")
        print("-"*45)
        for ticker, close, pct, vol in sorted_breakouts[:30]:  # Show top 30
            print(f"{ticker:12} | {close:8.2f} | {pct:+7.2f}% | {vol:10,d}")
        if len(sorted_breakouts) > 30:
            print(f"...and {len(sorted_breakouts) - 30} more breakouts.")
    else:
        print("No liquid breakouts found matching criteria.")

def main():
    tickers = fetch_all_nse_tickers()
    
    # Download stock tickers AND Nifty Index together
    all_tickers = tickers + ["^NSEI"]
    print(f"Downloading historical data for {len(all_tickers)} symbols using {NUM_THREADS} worker threads...")
    ticker_data_map = {}
    
    completed_count = 0
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(fetch_stock_data, t): t for t in all_tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                t, clean_data = future.result()
                ticker_data_map[t] = clean_data
            except Exception as e:
                ticker_data_map[ticker] = None
            completed_count += 1
            if completed_count % 100 == 0:
                print(f"Downloaded {completed_count}/{len(all_tickers)} symbols...")
                
    process_market_breadth(ticker_data_map)

if __name__ == "__main__":
    main()
