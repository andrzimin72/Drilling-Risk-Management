"""
State Checkpointing for Crash Recovery
Saves SwarmContext and AgentResults to SQLite after every agent completes.
Allows the swarm to resume exactly where it left off after a crash.
"""
from __future__ import annotations
import sqlite3
import json
import logging
import dataclasses
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class CheckpointManager:
    """Manages swarm state checkpoints in a local SQLite database."""
    
    def __init__(self, db_path: str | Path = ".cache/swarm_checkpoints.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        task_id TEXT PRIMARY KEY,
                        context_json TEXT,
                        status TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS agent_results (
                        task_id TEXT,
                        domain TEXT,
                        result_json TEXT,
                        saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (task_id, domain)
                    )
                """)
        except Exception as exc:
            logger.error(f"Failed to initialize checkpoint database: {exc}")

    def save_agent_result(self, task_id: str, domain: str, result: Any) -> None:
        """Save an agent's result to the checkpoint database."""
        try:
            # Convert dataclass to dict, handling non-serializable objects
            if dataclasses.is_dataclass(result) and not isinstance(result, type):
                data = dataclasses.asdict(result)
            else:
                data = result
            json_str = json.dumps(data, default=str, ensure_ascii=False)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO agent_results (task_id, domain, result_json) VALUES (?, ?, ?)",
                    (task_id, domain, json_str)
                )
                # Update checkpoint timestamp
                conn.execute(
                    "INSERT OR REPLACE INTO checkpoints (task_id, status, updated_at) VALUES (?, 'running', CURRENT_TIMESTAMP)",
                    (task_id,)
                )
            logger.debug(f"Checkpoint saved: {task_id}/{domain}")
        except Exception as exc:
            logger.warning(f"Failed to save checkpoint for {task_id}/{domain}: {exc}")

    def load_agent_results(self, task_id: str) -> dict[str, dict]:
        """Load all saved agent results for a task. Returns dict of domain -> result_dict."""
        results = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT domain, result_json FROM agent_results WHERE task_id = ?", (task_id,)
                ).fetchall()
            for domain, json_str in rows:
                try:
                    results[domain] = json.loads(json_str)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning(f"Failed to load checkpoints for {task_id}: {exc}")
        return results

    def get_status(self, task_id: str) -> str | None:
        """Get the current status of a task ('running', 'complete', or None)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT status FROM checkpoints WHERE task_id = ?", (task_id,)
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def mark_complete(self, task_id: str, context_summary: str = "") -> None:
        """Mark a task as complete."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO checkpoints (task_id, context_json, status, updated_at) VALUES (?, ?, 'complete', CURRENT_TIMESTAMP)",
                    (task_id, context_summary)
                )
        except Exception as exc:
            logger.warning(f"Failed to mark checkpoint complete for {task_id}: {exc}")

    def clear_checkpoint(self, task_id: str) -> None:
        """Remove all checkpoint data for a task."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM checkpoints WHERE task_id = ?", (task_id,))
                conn.execute("DELETE FROM agent_results WHERE task_id = ?", (task_id,))
        except Exception as exc:
            logger.warning(f"Failed to clear checkpoint for {task_id}: {exc}")