import pandas as pd
import numpy as np

def rank_universe_momentum(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Computes percentile ranks for 1M, 3M, and 6M returns,
    and calculates the overall Momentum Score based on weights.
    """
    if df.empty:
        return df
        
    df_ranked = df.copy()
    
    # Fill NaN returns with 0 so they don't break ranking
    for col in ["Return_1M", "Return_3M", "Return_6M", "Return_1Y", "Return_2Y"]:
        if col in df_ranked.columns:
            df_ranked[col] = df_ranked[col].fillna(0.0)
            
    # Calculate Percentile Ranks (0 to 100)
    df_ranked["Rank1M"] = df_ranked["Return_1M"].rank(pct=True) * 100
    df_ranked["Rank3M"] = df_ranked["Return_3M"].rank(pct=True) * 100
    df_ranked["Rank6M"] = df_ranked["Return_6M"].rank(pct=True) * 100
    
    if "Return_1Y" in df_ranked.columns:
        df_ranked["Rank1Y"] = df_ranked["Return_1Y"].rank(pct=True) * 100
    if "Return_2Y" in df_ranked.columns:
        df_ranked["Rank2Y"] = df_ranked["Return_2Y"].rank(pct=True) * 100
    
    # Load weights from config
    weights = config.get("ranking_weights", {})
    w1 = float(weights.get("weight_1m", 0.25))
    w3 = float(weights.get("weight_3m", 0.35))
    w6 = float(weights.get("weight_6m", 0.40))
    
    # Calculate Momentum Score
    df_ranked["Momentum_Score"] = (
        w1 * df_ranked["Rank1M"] + 
        w3 * df_ranked["Rank3M"] + 
        w6 * df_ranked["Rank6M"]
    )
    
    # Clean up and round ranks
    for col in ["Rank1M", "Rank3M", "Rank6M", "Rank1Y", "Rank2Y", "Momentum_Score"]:
        if col in df_ranked.columns:
            df_ranked[col] = df_ranked[col].round(2)
            
    # Calculate Percentile Ranks for Relative Strength Metrics
    rs_ranks = {
        "RS_Mansfield_Nifty500": "Rank_RS_Nifty500",
        "RS_Mansfield_Nifty50": "Rank_RS_Nifty50",
        "RS_Mansfield_Sector": "Rank_RS_Sector"
    }
    for rs_col, rank_col in rs_ranks.items():
        if rs_col in df_ranked.columns:
            # Fill NaNs with lowest value to put them at bottom of rank
            min_val = df_ranked[rs_col].min()
            fill_val = min_val - 1.0 if not pd.isna(min_val) else 0.0
            temp_series = df_ranked[rs_col].fillna(fill_val)
            df_ranked[rank_col] = (temp_series.rank(pct=True) * 100).round(2)
            
    return df_ranked
