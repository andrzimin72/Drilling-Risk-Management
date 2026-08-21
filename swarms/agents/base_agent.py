"""
Base Agent (Enterprise Edition)
Abstract base class for all specialist agents.
OpenTelemetry tracing for agents and parsers.
Includes SQLite caching, I/O retry logic, and async thread-pool execution.
"""
from __future__ import annotations
import asyncio
import functools
import hashlib
import json
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Pillar 3: Telemetry
from .telemetry import get_tracer, get_status_class

logger = logging.getLogger(__name__)
tracer = get_tracer("base_agent")
Status, StatusCode = get_status_class()

# ---------------------------------------------------------------------------
# Architectural Utilities: Cache & Retry
# ---------------------------------------------------------------------------
def retry_on_io_error(max_retries: int = 3, base_delay: float = 0.5):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OSError, IOError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
            raise last_exception
        return wrapper
    return decorator

class SQLiteCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "swarm_cache.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, mtime REAL, data TEXT)")

    def _get_key(self, file_path: Path, method_name: str) -> str:
        raw = f"{file_path.absolute()}_{method_name}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, file_path: Path, method_name: str) -> Any | None:
        if not file_path.exists(): return None
        mtime = file_path.stat().st_mtime
        key = self._get_key(file_path, method_name)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT mtime, data FROM cache WHERE key = ?", (key,)).fetchone()
            if row and row[0] == mtime:
                try: return json.loads(row[1])
                except Exception: return None
        return None

    def set(self, file_path: Path, method_name: str, data: Any):
        if not file_path.exists(): return
        mtime = file_path.stat().st_mtime
        key = self._get_key(file_path, method_name)
        try:
            serialized = json.dumps(data, default=str)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT OR REPLACE INTO cache (key, mtime, data) VALUES (?, ?, ?)",
                             (key, mtime, serialized))
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Core Agent Definitions
# ---------------------------------------------------------------------------
@dataclass
class AgentResult:
    agent_name: str
    domain: str
    status: str
    extracted_data: dict[str, Any] = field(default_factory=dict)
    tables: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    quality_flags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    duration_seconds: float = 0.0
    files_processed: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

class BaseAgent(ABC):
    domain: str = "unknown"
    description: str = ""

    def __init__(self, verbose: bool = False, cache_enabled: bool = True) -> None:
        self.verbose = verbose
        self.cache = SQLiteCache(Path(".cache/oil_gas_swarm")) if cache_enabled else None

    @abstractmethod
    def can_handle(self, file_info: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def _process(
        self,
        file_paths: list[Path],
        context: dict[str, Any],
    ) -> AgentResult:
        pass

    @retry_on_io_error(max_retries=3, base_delay=0.5)
    def _sync_parse(self, parser_instance: Any, method_name: str, path: Path, *args, **kwargs) -> Any:
        method = getattr(parser_instance, method_name)
        return method(path, *args, **kwargs)

    async def safe_parse(self, parser_instance: Any, method_name: str, path: Path, *args, **kwargs) -> Any:
        # Pillar 3: Trace every parser call
        span_name = f"parse.{method_name}"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("parse.file_name", path.name)
            span.set_attribute("parse.file_size_bytes", path.stat().st_size if path.exists() else 0)
            span.set_attribute("parse.method", method_name)
            
            # 1. Check Cache
            if self.cache:
                cached = self.cache.get(path, method_name)
                if cached is not None:
                    span.set_attribute("parse.cache_hit", True)
                    logger.debug(f"Cache HIT for {path.name} ({method_name})")
                    return cached
                span.set_attribute("parse.cache_hit", False)

            # 2. Run in background thread
            loop = asyncio.get_running_loop()
            try:
                result = await loop.run_in_executor(
                    None, self._sync_parse, parser_instance, method_name, path, *args, **kwargs
                )
                span.set_attribute("parse.status", "success")
            except Exception as e:
                span.set_attribute("parse.status", "error")
                span.set_attribute("parse.error", str(e))
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(e)
                logger.error(f"Failed to parse {path.name} after retries: {e}")
                raise

            # 3. Save to Cache
            if self.cache and result is not None:
                self.cache.set(path, method_name, result)
                
            return result

    async def run(
        self,
        file_paths: list[str | Path],
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        # Pillar 3: Trace every agent execution
        span_name = f"agent.{self.domain}"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("agent.name", self.__class__.__name__)
            span.set_attribute("agent.domain", self.domain)
            span.set_attribute("agent.file_count", len(file_paths))
            
            start = time.monotonic()
            paths = [Path(p) for p in file_paths]
            ctx = context or {}
            
            if not paths:
                span.set_attribute("agent.status", "skipped")
                return AgentResult(
                    agent_name=self.__class__.__name__,
                    domain=self.domain,
                    status="skipped",
                    summary=f"No files provided to {self.__class__.__name__}",
                )
                
            if self.verbose:
                logger.info(f"[{self.__class__.__name__}] Processing {len(paths)} file(s)...")
                
            try:
                result = await self._process(paths, ctx)
                span.set_attribute("agent.status", result.status)
                span.set_attribute("agent.confidence", result.confidence)
                span.set_attribute("agent.files_processed", len(result.files_processed))
                if result.quality_flags:
                    span.set_attribute("agent.quality_flags_count", len(result.quality_flags))
            except Exception as exc:
                span.set_attribute("agent.status", "error")
                span.set_attribute("agent.error", str(exc))
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exc)
                logger.exception(f"Agent {self.__class__.__name__} crashed")
                result = AgentResult(
                    agent_name=self.__class__.__name__,
                    domain=self.domain,
                    status="error",
                    error=str(exc),
                    summary=f"{self.__class__.__name__} failed: {exc}",
                    files_processed=[str(p) for p in paths],
                )
                
            result.duration_seconds = round(time.monotonic() - start, 3)
            span.set_attribute("agent.duration_seconds", result.duration_seconds)
            
            if self.verbose:
                logger.info(f"[{self.__class__.__name__}] Done in {result.duration_seconds}s — {result.status}")
            return result
