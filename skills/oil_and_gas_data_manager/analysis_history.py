"""
Analysis History Manager
Stores previous swarm analyses in SQLite for comparison and trend tracking.
"""
from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AnalysisHistory:
    """Manages persistent storage of analysis results."""

    def __init__(self, db_path: str | Path = ".cache/analysis_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE NOT NULL,
                    well_name TEXT,
                    pad_name TEXT,
                    operator TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    files_processed INTEGER DEFAULT 0,
                    elapsed_seconds REAL DEFAULT 0,
                    agents_succeeded INTEGER DEFAULT 0,
                    agents_failed INTEGER DEFAULT 0,
                    risk_summary TEXT,
                    risk_registry TEXT,
                    metrics TEXT,
                    report_path TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_well ON analyses(well_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created ON analyses(created_at DESC)"
            )

    def save_analysis(
        self,
        task_id: str,
        well_name: Optional[str],
        pad_name: Optional[str],
        operator: Optional[str],
        files_processed: int,
        elapsed_seconds: float,
        agents_succeeded: int,
        agents_failed: int,
        risk_summary: dict,
        risk_registry_data: list[dict],
        metrics: dict,
        report_path: Optional[str] = None,
    ) -> None:
        """Save a completed analysis to history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO analyses (
                        task_id, well_name, pad_name, operator,
                        files_processed, elapsed_seconds,
                        agents_succeeded, agents_failed,
                        risk_summary, risk_registry, metrics, report_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id, well_name, pad_name, operator,
                        files_processed, elapsed_seconds,
                        agents_succeeded, agents_failed,
                        json.dumps(risk_summary, ensure_ascii=False, default=str),
                        json.dumps(risk_registry_data, ensure_ascii=False, default=str),
                        json.dumps(metrics, ensure_ascii=False, default=str),
                        report_path,
                    ),
                )
            logger.info(f"Analysis {task_id} saved to history")
        except Exception as exc:
            logger.error(f"Failed to save analysis to history: {exc}")

    def list_analyses(self, limit: int = 50) -> list[dict]:
        """List recent analyses (metadata only, no heavy JSON)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, task_id, well_name, pad_name, operator, created_at,
                       files_processed, elapsed_seconds, agents_succeeded, agents_failed
                FROM analyses
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def load_analysis(self, task_id: str) -> Optional[dict]:
        """Load full analysis data including risk registry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM analyses WHERE task_id = ?", (task_id,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        # Parse JSON fields
        for field in ("risk_summary", "risk_registry", "metrics"):
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    result[field] = {}
        return result

    def get_well_names(self) -> list[str]:
        """Get distinct well names for comparison dropdown."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT well_name FROM analyses "
                "WHERE well_name IS NOT NULL AND well_name != '' "
                "ORDER BY well_name"
            ).fetchall()
        return [r[0] for r in rows]

    def get_latest_for_wells(self, well_names: list[str]) -> list[dict]:
        """Get the most recent analysis for each specified well."""
        results = []
        for well in well_names:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT * FROM analyses
                    WHERE well_name = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (well,),
                ).fetchone()
            if row:
                data = dict(row)
                for field in ("risk_summary", "risk_registry", "metrics"):
                    if data.get(field):
                        try:
                            data[field] = json.loads(data[field])
                        except (json.JSONDecodeError, TypeError):
                            data[field] = {}
                results.append(data)
        return results

    def delete_analysis(self, task_id: str) -> bool:
        """Delete an analysis from history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM analyses WHERE task_id = ?", (task_id,)
                )
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to delete analysis: {exc}")
            return False

    def get_trend_data(self, well_name: str) -> list[dict]:
        """Get chronological analysis data for trend charts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT task_id, created_at, risk_summary, metrics
                FROM analyses
                WHERE well_name = ?
                ORDER BY created_at ASC
                """,
                (well_name,),
            ).fetchall()
        results = []
        for row in rows:
            data = dict(row)
            for field in ("risk_summary", "metrics"):
                if data.get(field):
                    try:
                        data[field] = json.loads(data[field])
                    except (json.JSONDecodeError, TypeError):
                        data[field] = {}
            results.append(data)
        return results


def extract_metrics_from_result(swarm_result: Any, registry: Any) -> dict:
    """
    Extract key comparison metrics from a SwarmResult.
    Used for well comparison and trend charts.
    """
    metrics: dict[str, Any] = {}

    # Risk metrics
    if registry:
        summary = registry.get_summary()
        metrics["total_risks"] = summary.get("total_risks", 0)
        metrics["critical_risks"] = summary.get("critical_count", 0)
        metrics["high_risks"] = summary.get("high_count", 0)
        metrics["medium_risks"] = summary.get("by_level", {}).get("medium", 0)
        metrics["low_risks"] = summary.get("by_level", {}).get("low", 0)
        metrics["risk_score"] = summary.get("risk_score", 0)

    # Agent-level metrics
    agent_results = getattr(swarm_result, "agent_results", {})

    # Drilling metrics
    drilling = agent_results.get("drilling", {})
    if isinstance(drilling, dict):
        drill_data = drilling.get("extracted_data", {}).get("drilling", {})
        metrics["npt_hours"] = drill_data.get("npt_hours", 0) or 0
        metrics["npt_events"] = len(drill_data.get("npt_events", []))
        metrics["current_depth"] = (
            drill_data.get("current_depth_m")
            or drill_data.get("measured_depth_m")
            or drill_data.get("current_depth_ft")
            or 0
        )
        metrics["rop"] = (
            drill_data.get("rop_m_hr") or drill_data.get("rop_ft_hr") or 0
        )
        metrics["mud_weight"] = (
            drill_data.get("mud_weight_sg")
            or drill_data.get("mud_weight_ppg")
            or 0
        )

    # Directional metrics
    directional = agent_results.get("directional", {})
    if isinstance(directional, dict):
        dir_data = directional.get("extracted_data", {}).get("directional", {})
        metrics["max_dls"] = dir_data.get("max_dls", 0) or 0
        metrics["max_inclination"] = dir_data.get("max_inc_deg", 0) or 0
        metrics["total_md"] = dir_data.get("total_md", 0) or 0
        metrics["total_tvd"] = dir_data.get("total_tvd", 0) or 0
        # Store stations for DLS trend chart
        stations = dir_data.get("stations", [])
        if stations:
            metrics["dls_stations"] = [
                {"md": s.get("md", 0), "dls": s.get("dls", 0)}
                for s in stations[:200]  # Cap for storage
            ]

    # Logs metrics
    logs = agent_results.get("logs", {})
    if isinstance(logs, dict):
        log_data = logs.get("extracted_data", {}).get("logs", {})
        metrics["total_net_pay"] = log_data.get("total_net_pay", 0) or 0
        metrics["pay_zone_count"] = log_data.get("pay_zone_count", 0) or 0

    # Completions metrics
    completions = agent_results.get("completions", {})
    if isinstance(completions, dict):
        comp_data = completions.get("extracted_data", {}).get("completions", {})
        metrics["stage_count"] = (
            comp_data.get("stage_count")
            or comp_data.get("stage_count_actual")
            or 0
        )

    # Production metrics
    production = agent_results.get("production", {})
    if isinstance(production, dict):
        prod_data = production.get("extracted_data", {}).get("production", {})
        ip_metrics = prod_data.get("ip_metrics", {})
        metrics["ip30"] = (
            ip_metrics.get("ip30_rate") or ip_metrics.get("ip30_bopd") or 0
        )
        metrics["ip90"] = (
            ip_metrics.get("ip90_rate") or ip_metrics.get("ip90_bopd") or 0
        )

    # HSE metrics
    hse = agent_results.get("hse", {})
    if isinstance(hse, dict):
        hse_data = hse.get("extracted_data", {}).get("hse", {})
        metrics["hse_incidents"] = sum(
            hse_data.get("incident_counts", {}).values()
        )
        metrics["hse_npt_hours"] = hse_data.get("total_npt_hse_hrs", 0) or 0

    # NPT events detail for Pareto chart
    if isinstance(drilling, dict):
        drill_data = drilling.get("extracted_data", {}).get("drilling", {})
        npt_events = drill_data.get("npt_events", [])
        if npt_events:
            metrics["npt_event_details"] = [
                {
                    "description": e.get("description", "")[:100],
                    "duration": e.get("duration_hrs") or 0,
                }
                for e in npt_events
            ]

    return metrics