"""
Structured Logging Setup
Replaces print() statements with proper enterprise logging.
"""
from __future__ import annotations
import logging
import sys

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Create a standardized logger for agents and parsers."""
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger

# Convenience function for quick imports
def get_logger(name: str) -> logging.Logger:
    from .config import CONFIG
    return setup_logger(name, CONFIG.log_level)