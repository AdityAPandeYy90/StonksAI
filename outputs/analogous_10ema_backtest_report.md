# Analogous Decision Trees Backtest Report (10 EMA Trailing Exit)

Generated on: 2026-08-16 23:30:54

- **Exit Rule:** Trailed every trade using 10-Day EMA until the first Daily Close below 10 EMA.
- **Leaf Tiers:** FULL (1.0x), HALF 2 (0.66x), HALF 1 (0.33x), SKIP (0.0x).

## Strategy Performance Comparison

| Strategy Tree | Total Trades | Win Rate (%) | Avg Holding Days | Avg Raw Return | Avg Weighted Return | Profit Factor |
|---|---|---|---|---|---|---|
| User Handwritten Tree | 13117 | 35.04% | 8.8 Days | +2.02% | +1.32% | 1.55 |
| Proposed Tree (Analogous) | 1807 | 33.92% | 9.1 Days | +3.35% | +1.37% | 1.65 |
