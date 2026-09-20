import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
from google import genai
from google.genai import types
from requests.adapters import HTTPAdapter

# Setup a session that disables HTTP retries to prevent yfinance from stalling on rate limits
yf_session = requests.Session()
yf_session.mount("https://", HTTPAdapter(max_retries=0))
yf_session.mount("http://", HTTPAdapter(max_retries=0))

def get_yahoo_ticker(screener_symbol: str) -> str:
    """
    Finds the correct Yahoo Finance ticker symbol for a given Screener symbol.
    Prefers NSE (.NS) and falls back to search.
    """
    # 1. Try default NSE symbol
    symbol_ns = f"{screener_symbol.upper()}.NS"
    try:
        ticker = yf.Ticker(symbol_ns, session=yf_session)
        # Fetch tiny history to check if symbol is valid
        hist = ticker.history(period="1d")
        if not hist.empty:
            return symbol_ns
    except Exception:
        pass
    
    # 2. Try default BSE symbol
    symbol_bo = f"{screener_symbol.upper()}.BO"
    try:
        ticker = yf.Ticker(symbol_bo, session=yf_session)
        hist = ticker.history(period="1d")
        if not hist.empty:
            return symbol_bo
    except Exception:
        pass

    # 3. Fallback: Search Yahoo Finance API
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={screener_symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            quotes = data.get("quotes", [])
            # Search for first Indian quote (.NS or .BO)
            for q in quotes:
                symbol = q.get("symbol", "")
                if symbol.endswith(".NS") or symbol.endswith(".BO"):
                    return symbol
            # If no Indian symbol, return first quote symbol
            if quotes:
                return quotes[0].get("symbol", "")
    except Exception as e:
        print(f"Error in Yahoo ticker search: {e}")
        
    return symbol_ns  # Default fallback

def calculate_relative_strength(ticker_symbol: str):
    """
    Fetches 1-year history for the stock and Nifty 50 (^NSEI) and computes:
    - Return comparisons over 1M, 3M, 6M, 1Y
    - Data points for the Relative Strength (RS) Line: (Stock / Nifty50) * 1000
    """
    try:
        stock = yf.Ticker(ticker_symbol, session=yf_session)
        nifty = yf.Ticker("^NSEI", session=yf_session)
        
        # Fetch 1 year of daily historical data
        stock_hist = stock.history(period="1y")
        nifty_hist = nifty.history(period="1y")
        
        if stock_hist.empty or nifty_hist.empty:
            raise Exception("Empty historical data returned from Yahoo Finance.")
            
        # Align date indices (inner join)
        merged = pd.merge(
            stock_hist[["Close"]].rename(columns={"Close": "Stock"}),
            nifty_hist[["Close"]].rename(columns={"Close": "Nifty"}),
            left_index=True,
            right_index=True,
            how="inner"
        )
        
        if merged.empty:
            raise Exception("No overlapping dates found between stock and Nifty 50.")
            
        # Calculate Returns
        # Helper to get return over a specific window of trading days
        def get_return(df, days):
            if len(df) < days:
                return None
            start_price = df.iloc[-days]["Stock"]
            end_price = df.iloc[-1]["Stock"]
            stock_ret = ((end_price - start_price) / start_price) * 100
            
            start_nifty = df.iloc[-days]["Nifty"]
            end_nifty = df.iloc[-1]["Nifty"]
            nifty_ret = ((end_nifty - start_nifty) / start_nifty) * 100
            
            return {
                "stock_return": round(stock_ret, 2),
                "nifty_return": round(nifty_ret, 2),
                "outperformance": round(stock_ret - nifty_ret, 2)
            }
            
        # Returns for 1M (21 days), 3M (63 days), 6M (126 days), 1Y (252 days)
        returns = {
            "1m": get_return(merged, min(21, len(merged))),
            "3m": get_return(merged, min(63, len(merged))),
            "6m": get_return(merged, min(126, len(merged))),
            "1y": get_return(merged, min(252, len(merged)))
        }
        
        # Calculate RS Line: (Stock / Nifty) * 1000
        merged["RS_Line"] = (merged["Stock"] / merged["Nifty"]) * 1000
        
        # Calculate RS Rating relative to itself (trend)
        # Standardize RS Line to start at 100 for visualization
        initial_rs = merged["RS_Line"].iloc[0]
        merged["RS_Line_Norm"] = (merged["RS_Line"] / initial_rs) * 100
        
        # Downsample to weekly data points (every 5 trading days) to save bandwidth & make chart clean
        downsampled = merged.iloc[::5]
        # Include the very last day
        if len(merged) % 5 != 1:
            downsampled = pd.concat([downsampled, merged.iloc[[-1]]])
            
        chart_data = []
        for date, row in downsampled.iterrows():
            chart_data.append({
                "date": date.strftime("%Y-%m-%d"),
                "stock_price": round(row["Stock"], 2),
                "nifty_price": round(row["Nifty"], 2),
                "rs_line": round(row["RS_Line"], 2),
                "rs_line_norm": round(row["RS_Line_Norm"], 2)
            })
            
        # Calculate Current relative strength trend
        # If RS line is up over 3M, stock is showing relative strength
        rs_3m = returns["3m"]
        rs_trend = "Neutral"
        if rs_3m:
            rs_trend = "Bullish" if rs_3m["outperformance"] > 5 else ("Bearish" if rs_3m["outperformance"] < -5 else "Neutral")
            
        return {
            "current_price": round(merged["Stock"].iloc[-1], 2),
            "returns": returns,
            "rs_trend": rs_trend,
            "chart_data": chart_data
        }
        
    except Exception as e:
        print(f"Error calculating relative strength: {e}")
        return {
            "current_price": 0.0,
            "returns": {"1m": None, "3m": None, "6m": None, "1y": None},
            "rs_trend": "Unknown",
            "chart_data": [],
            "error": str(e)
        }

def fetch_stock_news(ticker_symbol: str):
    """
    Fetches news from Yahoo Finance for the given ticker symbol.
    """
    try:
        ticker = yf.Ticker(ticker_symbol, session=yf_session)
        news = ticker.news
        if not news:
            return []
            
        formatted_news = []
        for n in news[:8]:  # Limit to top 8 news items
            formatted_news.append({
                "title": n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "link": n.get("link", ""),
                "time": n.get("providerPublishTime", 0)
            })
        return formatted_news
    except Exception as e:
        print(f"Error fetching news for {ticker_symbol}: {e}")
        return []

def get_gemini_analysis(api_key: str, stock_data: dict, news_items: list) -> dict:
    """
    Uses Gemini API (gemini-2.5-flash) to generate a structured analysis of the stock,
    including the story, policy changes, new products, guidance, and sector theme.
    """
    if not api_key:
        return get_mock_analysis(stock_data["symbol"])
        
    client = genai.Client(api_key=api_key)
    
    # Prepare financial snapshot for prompt
    financials_summary = ""
    for q in stock_data.get("quarterly_financials", []):
        financials_summary += f"Quarter: {q['quarter']}, Sales: {q['sales']} Cr, NPM: {q['npm_percent']}%, EPS: {q['eps']}\n"
        
    news_summary = ""
    for idx, item in enumerate(news_items):
        news_summary += f"{idx+1}. {item['title']} (Source: {item['publisher']})\n"
        
    prompt = f"""
    You are an expert Indian Stock Market Equity Analyst. Your task is to provide a comprehensive, deep-dive analysis of {stock_data['symbol']}.
    
    Here is the company data:
    - Symbol: {stock_data['symbol']}
    - Sector: {stock_data['sector']}
    - Industry: {stock_data['industry']}
    - Profile: {stock_data['about']}
    
    Here is their recent Quarterly Financial performance (last 6 quarters):
    {financials_summary}
    
    Here are the recent news headlines:
    {news_summary}
    
    Based on the above, synthesize the following structured analysis. 
    Your response MUST be in raw JSON format, strictly matching this schema. Do not enclose it in markdown ```json blocks. Just output the JSON.
    
    JSON Schema:
    {{
        "story": "A compelling, concise summary (100-150 words) explaining what this company does, its core business drivers, and the narrative around the stock right now.",
        "policy_changes": [
            {{
                "policy_name": "Name of the government regulation, tax policy, or industry policy change affecting the stock. If no recent policy, mention a macroeconomic driver.",
                "impact": "Good" or "Bad" or "Neutral",
                "rationale": "Detail explaining why this is good or bad for the stock and how it impacts their operations."
            }}
        ],
        "eventful_updates": [
            {{
                "event_name": "Description of a new product launch, capacity expansion, order win, or major event.",
                "description": "Elaborate on the significance of this update."
            }}
        ],
        "estimates_guidance": [
            {{
                "source": "Consensus/Brokerage view or management statements",
                "forecast": "What is the earnings guidance or outlook?",
                "target_price": "Expected target price range or growth target"
            }}
        ],
        "sector_theme": {{
            "status": "Hot" or "Warm" or "Not",
            "rationale": "Provide the rationale explaining why this sector theme is hot or not right now, citing valuation, government focus, or tailwinds/headwinds."
        }}
    }}
    
    Ensure that the content is factual, highly professional, and customized to this specific stock. If details are missing from news, use your knowledge base of Indian stock market developments as of mid-2026.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        # Parse the JSON response
        text = response.text.strip()
        # Clean up any accidental markdown wrapper
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return get_mock_analysis(stock_data["symbol"])

def get_mock_analysis(symbol: str) -> dict:
    """Fallback mock analysis if Gemini API is not available or fails."""
    return {
        "story": f"Mock Story: {symbol} is a leading player in its sector. The company has been expanding its operations and leveraging domestic growth. Currently, it faces general market dynamics, balancing competitive pressures against high demand.",
        "policy_changes": [
            {
                "policy_name": "GST / Custom Duties Adjustments",
                "impact": "Neutral",
                "rationale": "Recent adjustments in custom duties have minor positive impacts on raw material costs, offset by rising compliance measures."
            },
            {
                "policy_name": "PLI Scheme Support",
                "impact": "Good",
                "rationale": "Government push on manufacturing is beneficial for long-term production incentives if the company qualifies."
            }
        ],
        "eventful_updates": [
            {
                "event_name": "Service Expansion",
                "description": "The company has launched new digital products to improve customer retention and expand market share."
            }
        ],
        "estimates_guidance": [
            {
                "source": "Consensus Estimates",
                "forecast": "Expected revenue growth of 12-15% YoY for the next fiscal year, with stable margins.",
                "target_price": "Trading near historical averages, target projections indicate moderate single-digit upside."
            }
        ],
        "sector_theme": {
            "status": "Warm",
            "rationale": "The sector has solid structural tailwinds from domestic consumption but suffers from short-term inflation headwinds and high valuations relative to peers."
        }
    }
