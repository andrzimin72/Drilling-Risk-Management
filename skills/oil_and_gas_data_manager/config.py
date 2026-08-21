"""
Centralized Configuration
Loads settings from config.yaml or uses defaults.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os

@dataclass
class AppConfig:
    # Petrophysics (Phase 2 defaults)
    gr_cutoff: float = 75.0
    rt_cutoff: float = 10.0
    
    # Caching & Performance
    cache_enabled: bool = True
    cache_dir: Path = Path(".cache/oil_gas_swarm")
    max_table_rows: int = 5000
    
    # Resilience (Retries for flaky network drives)
    max_retries: int = 3
    retry_base_delay: float = 0.5
    
    # Observability
    log_level: str = "INFO"
    
    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "AppConfig":
        """Load config from YAML if available, otherwise use defaults."""
        path = Path(config_path) if config_path else Path("config.yaml")
        
        if path.exists():
            try:
                import yaml
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except ImportError:
                pass  # Fallback to defaults if pyyaml isn't installed
            except Exception:
                pass
                
        return cls()

# Global singleton
CONFIG = AppConfig.load()