import os
import sys
import logging
import yaml
from pathlib import Path

def get_project_root() -> Path:
    """Returns the root path of the momentum_screener project."""
    # This file is in momentum_screener/src/utils.py
    return Path(__file__).resolve().parent.parent

def setup_directories(config: dict) -> dict:
    """Creates the data, output, and log folders if they do not exist."""
    root = get_project_root()
    
    # Map relative paths from config to absolute paths
    paths = {
        "data_dir": root / config.get("data_dir", "data"),
        "raw_dir": root / config.get("data_dir", "data") / "raw",
        "cache_dir": root / config.get("data_dir", "data") / "cache",
        "output_dir": root / config.get("output_dir", "outputs"),
        "log_dir": root / config.get("log_dir", "logs")
    }
    
    for name, path in paths.items():
        os.makedirs(path, exist_ok=True)
        
    return paths

def setup_logger(log_dir: Path) -> logging.Logger:
    """Configures logging to both console and file in log_dir."""
    logger = logging.getLogger("MomentumScreener")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if logger was already setup
    if logger.handlers:
        return logger
        
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    log_file = log_dir / "screener.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

def load_config() -> dict:
    """Loads configuration yaml file and returns it as a dict."""
    root = get_project_root()
    config_path = root / "config" / "settings.yaml"
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    return config
