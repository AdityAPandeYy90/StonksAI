# Indian Momentum Screener -- Implementation Plan

## Objective

Build a Python-based end-of-day momentum screener for Indian (NSE)
stocks that replicates the workflow used by Qullamaggie/TC2000 while
remaining independent of TC2000, Chartink, or TradingView limitations.

### Daily Workflow

1.  Download/update all NSE stock data.
2.  Compute technical indicators.
3.  Rank all stocks by:
    -   1 Month Momentum
    -   3 Month Momentum
    -   6 Month Momentum
4.  Keep only the strongest 7% (configurable).
5.  Export watchlists.
6.  Review charts manually for VCPs, tight consolidations, and breakout
    setups.

------------------------------------------------------------------------

# Technology Stack

-   Python 3.11+
-   pandas
-   numpy
-   yfinance (default data provider)
-   pandas-ta or ta
-   scipy
-   joblib
-   tqdm
-   pyarrow
-   openpyxl

Outputs:

-   CSV
-   Excel
-   JSON
-   TradingView Watchlist CSV

------------------------------------------------------------------------

# Project Structure

``` text
momentum_screener/

config/
    settings.yaml

data/
    raw/
    processed/
    cache/

logs/

outputs/

src/
    download.py
    indicators.py
    ranking.py
    filters.py
    screener.py
    export.py
    utils.py

main.py
```

------------------------------------------------------------------------

# Phase 1 -- Universe Construction

Automatically build the NSE stock universe.

Store:

-   Ticker
-   Company Name
-   Sector
-   Industry

Ticker format:

``` text
RELIANCE.NS
TCS.NS
HDFCBANK.NS
```

Universe size:

Approximately 1800--2200 stocks.

------------------------------------------------------------------------

# Phase 2 -- Data Download

Download daily OHLCV data.

Fields:

-   Open
-   High
-   Low
-   Close
-   Volume

History:

Minimum 400 trading days.

Requirements:

-   Incremental updates
-   Local caching
-   Parallel downloads
-   Avoid duplicate downloads

------------------------------------------------------------------------

# Phase 3 -- Indicator Engine

## Trend

-   EMA21
-   SMA21
-   SMA50
-   SMA150
-   SMA200

## Volatility

-   ATR(21)
-   ATR%(21)
-   ADR(21)
-   Daily Range %

## Liquidity

Dollar Volume

    Close × Volume

Average Dollar Volume

    50-day average

Average Volume

-   20-day
-   50-day

## Returns

-   1 Week
-   2 Week
-   1 Month (21 days)
-   3 Months (63 days)
-   6 Months (126 days)
-   1 Year (252 days)

## Distance Metrics

-   Price vs EMA21
-   Price vs SMA50
-   Price vs SMA200
-   Distance from 52-week High
-   Distance from 52-week Low

------------------------------------------------------------------------

# Phase 4 -- Relative Strength Ranking

For every stock compute percentile ranks.

-   Rank1M
-   Rank3M
-   Rank6M

Best performer = 100

Worst performer = 0

This reproduces TC2000's ranking concept.

------------------------------------------------------------------------

# Phase 5 -- Momentum Score

Default formula:

    Momentum Score

    =
    0.25 × Rank1M
    +
    0.35 × Rank3M
    +
    0.40 × Rank6M

Weights should be configurable.

------------------------------------------------------------------------

# Phase 6 -- Filters

## Trend

-   Price \> EMA21 × 1.01
-   Price \> SMA50 × 1.01
-   Price \> SMA200 × 1.01

## Liquidity

50-Day Average Dollar Volume ≥ ₹75 Crore

(Configurable)

## Volatility

ATR%(21) ≥ 2.5%

(Configurable)

## Price

Minimum Price

Default:

₹100

(Configurable)

------------------------------------------------------------------------

# Phase 7 -- Screens

## 1-Month Momentum

Top 7%

Sorted by Rank1M

------------------------------------------------------------------------

## 3-Month Momentum

Top 7%

Sorted by Rank3M

------------------------------------------------------------------------

## 6-Month Momentum

Top 7%

Sorted by Rank6M

------------------------------------------------------------------------

## Combined Momentum

Sorted by Momentum Score

------------------------------------------------------------------------

## Intersection List

Stocks appearing in:

-   1M
-   3M
-   6M

These are often the strongest institutional leaders.

------------------------------------------------------------------------

# Phase 8 -- Setup Detection (Future Module)

Detect:

-   Volatility Contraction Pattern (VCP)
-   NR7
-   Inside Day
-   Pocket Pivot
-   Volume Dry-Up
-   Tight Range
-   Breakout
-   Gap Up
-   EMA Bounce

Produce a Setup Score.

------------------------------------------------------------------------

# Phase 9 -- Export

Generate:

-   CSV
-   Excel
-   JSON
-   TradingView Watchlist
-   Markdown Summary

Suggested columns:

-   Ticker
-   Company
-   Momentum Score
-   Rank1M
-   Rank3M
-   Rank6M
-   ATR%
-   ADR%
-   Average Dollar Volume
-   Price vs EMA21
-   Price vs SMA50
-   Price vs SMA200
-   Distance to 52W High
-   Setup Score

------------------------------------------------------------------------

# Configuration

Everything should be configurable through `settings.yaml`.

Examples:

-   Universe
-   Top %
-   ATR threshold
-   ADR threshold
-   Dollar Volume threshold
-   Minimum Price
-   Ranking weights
-   Output paths

------------------------------------------------------------------------

# Performance Goals

Universe:

\~2000 stocks

Daily runtime:

\< 5 minutes

Requirements:

-   Parallel downloads
-   Incremental updates
-   Local cache
-   Efficient calculations

------------------------------------------------------------------------

# Future Enhancements

-   Sector Relative Strength
-   Industry Relative Strength
-   Relative Strength vs Nifty 50
-   Relative Volume Ranking
-   Earnings Calendar
-   Institutional Accumulation Score
-   Telegram Notifications
-   Discord Notifications
-   Web Dashboard
-   Historical Backtesting

------------------------------------------------------------------------

# Recommended Implementation Order

1.  Universe management
2.  Data download
3.  Local cache
4.  Indicator engine
5.  Ranking engine
6.  Filtering engine
7.  Export system
8.  Configuration management
9.  Setup detection
10. Backtesting

------------------------------------------------------------------------

# Notes

This project intentionally separates:

-   **Momentum Universe Creation** (objective ranking of stocks)
-   **Trade Setup Detection** (VCPs, consolidations, breakouts)

The screener should first identify the strongest stocks based on
momentum, liquidity, and volatility. Manual chart review or a later
setup-detection module can then identify actionable entries, closely
mirroring Qullamaggie's workflow while remaining tailored to the Indian
market.
