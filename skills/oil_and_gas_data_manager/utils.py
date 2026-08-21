import sqlite3
import hashlib
import json
from pathlib import Path
from typing import Any

class SQLiteCache:
    """
    Enterprise-grade cache using SQLite.
    Solves file-locking issues, supports concurrent reads/writes,
    and is significantly faster than JSON files on network drives.
    """
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "swarm_cache.db"
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database and table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    mtime REAL,
                    data TEXT
                )
            """)
            # Index for fast lookups
            conn.execute("CREATE INDEX IF NOT EXISTS idx_key ON cache(key)")

    def _get_key(self, file_path: Path, method_name: str) -> str:
        """Generate a unique hash key based on file path and method."""
        raw = f"{file_path.absolute()}_{method_name}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, file_path: Path, method_name: str) -> Any | None:
        """Retrieve cached data if the file hasn't been modified."""
        if not file_path.exists():
            return None
        mtime = file_path.stat().st_mtime
        key = self._get_key(file_path, method_name)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT mtime, data FROM cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            # Check if file modification time matches the cached time
            if row and row[0] == mtime:
                try:
                    return json.loads(row[1])
                except Exception:
                    return None
        return None

    def set(self, file_path: Path, method_name: str, data: Any):
        """Save data to the cache, automatically invalidating old versions."""
        if not file_path.exists():
            return
        mtime = file_path.stat().st_mtime
        key = self._get_key(file_path, method_name)
        serialized = json.dumps(data, default=str)
        
        # INSERT OR REPLACE handles concurrent updates safely
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, mtime, data) VALUES (?, ?, ?)",
                (key, mtime, serialized)
            )