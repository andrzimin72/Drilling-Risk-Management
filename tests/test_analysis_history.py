"""
Tests for the Analysis History manager (SQLite persistence).
"""
import pytest
from pathlib import Path
from skills.oil_and_gas_data_manager.analysis_history import (
    AnalysisHistory, extract_metrics_from_result
)


class TestAnalysisHistory:
    def test_init_creates_db(self, tmp_path):
        db_path = tmp_path / "test_history.db"
        history = AnalysisHistory(db_path)
        assert db_path.exists()

    def test_save_and_load_analysis(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        history.save_analysis(
            task_id="task_001",
            well_name="Well 123",
            pad_name="Pad 5",
            operator="Gazprom Neft",
            files_processed=10,
            elapsed_seconds=45.2,
            agents_succeeded=6,
            agents_failed=0,
            risk_summary={"total_risks": 5, "critical_count": 1},
            risk_registry_data=[{"risk_id": "RISK-001", "title_en": "Test"}],
            metrics={"npt_hours": 12.5, "max_dls": 8.5},
        )

        loaded = history.load_analysis("task_001")
        assert loaded is not None
        assert loaded["well_name"] == "Well 123"
        assert loaded["files_processed"] == 10
        assert loaded["risk_summary"]["total_risks"] == 5
        assert loaded["metrics"]["npt_hours"] == 12.5

    def test_list_analyses(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        for i in range(5):
            history.save_analysis(
                task_id=f"task_{i:03d}",
                well_name=f"Well {i}",
                pad_name="Pad 1",
                operator="Test",
                files_processed=i + 1,
                elapsed_seconds=10.0,
                agents_succeeded=5,
                agents_failed=0,
                risk_summary={},
                risk_registry_data=[],
                metrics={},
            )

        analyses = history.list_analyses()
        assert len(analyses) == 5
        # Should be ordered by created_at DESC
        assert analyses[0]["task_id"] == "task_004"

    def test_list_analyses_limit(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        for i in range(10):
            history.save_analysis(
                task_id=f"task_{i:03d}",
                well_name=f"Well {i}",
                pad_name="Pad 1",
                operator="Test",
                files_processed=1,
                elapsed_seconds=1.0,
                agents_succeeded=1,
                agents_failed=0,
                risk_summary={},
                risk_registry_data=[],
                metrics={},
            )

        analyses = history.list_analyses(limit=3)
        assert len(analyses) == 3

    def test_get_well_names(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        for well in ["Well A", "Well B", "Well A"]:  # Well A appears twice
            history.save_analysis(
                task_id=f"task_{well}_{id(well)}",
                well_name=well,
                pad_name="Pad 1",
                operator="Test",
                files_processed=1,
                elapsed_seconds=1.0,
                agents_succeeded=1,
                agents_failed=0,
                risk_summary={},
                risk_registry_data=[],
                metrics={},
            )

        wells = history.get_well_names()
        assert "Well A" in wells
        assert "Well B" in wells
        assert len(wells) == 2  # Distinct

    def test_get_latest_for_wells(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        # Save multiple analyses for Well A
        history.save_analysis(
            task_id="task_a_old",
            well_name="Well A",
            pad_name="Pad 1",
            operator="Test",
            files_processed=1,
            elapsed_seconds=1.0,
            agents_succeeded=1,
            agents_failed=0,
            risk_summary={"total_risks": 10},
            risk_registry_data=[],
            metrics={"npt_hours": 20.0},
        )
        history.save_analysis(
            task_id="task_a_new",
            well_name="Well A",
            pad_name="Pad 1",
            operator="Test",
            files_processed=2,
            elapsed_seconds=2.0,
            agents_succeeded=2,
            agents_failed=0,
            risk_summary={"total_risks": 5},
            risk_registry_data=[],
            metrics={"npt_hours": 10.0},
        )

        results = history.get_latest_for_wells(["Well A"])
        assert len(results) == 1
        assert results[0]["task_id"] == "task_a_new"
        assert results[0]["risk_summary"]["total_risks"] == 5

    def test_delete_analysis(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        history.save_analysis(
            task_id="task_to_delete",
            well_name="Well X",
            pad_name="Pad 1",
            operator="Test",
            files_processed=1,
            elapsed_seconds=1.0,
            agents_succeeded=1,
            agents_failed=0,
            risk_summary={},
            risk_registry_data=[],
            metrics={},
        )

        assert history.delete_analysis("task_to_delete")
        assert history.load_analysis("task_to_delete") is None

    def test_load_nonexistent_returns_none(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        assert history.load_analysis("nonexistent") is None

    def test_get_trend_data(self, tmp_path):
        history = AnalysisHistory(tmp_path / "history.db")
        for i in range(3):
            history.save_analysis(
                task_id=f"task_trend_{i}",
                well_name="Well Trend",
                pad_name="Pad 1",
                operator="Test",
                files_processed=i + 1,
                elapsed_seconds=float(i),
                agents_succeeded=1,
                agents_failed=0,
                risk_summary={"total_risks": 10 - i * 2},
                risk_registry_data=[],
                metrics={"npt_hours": 20.0 - i * 5},
            )

        trends = history.get_trend_data("Well Trend")
        assert len(trends) == 3
        # Should be ordered chronologically
        assert trends[0]["risk_summary"]["total_risks"] == 10
        assert trends[2]["risk_summary"]["total_risks"] == 6


class TestExtractMetrics:
    def test_extract_from_empty_result(self):
        class EmptyResult:
            agent_results = {}
        metrics = extract_metrics_from_result(EmptyResult(), None)
        assert metrics == {}

    def test_extract_drilling_metrics(self):
        class MockResult:
            agent_results = {
                "drilling": {
                    "extracted_data": {"drilling": {
                        "npt_hours": 12.5,
                        "npt_events": [{"description": "Pump failure", "duration_hrs": 12.5}],
                        "current_depth_m": 3000.0,
                        "rop_m_hr": 45.0,
                    }}
                }
            }
        metrics = extract_metrics_from_result(MockResult(), None)
        assert metrics["npt_hours"] == 12.5
        assert metrics["current_depth"] == 3000.0
        assert metrics["rop"] == 45.0

    def test_extract_directional_metrics(self):
        class MockResult:
            agent_results = {
                "directional": {
                    "extracted_data": {"directional": {
                        "max_dls": 8.5,
                        "max_inc_deg": 90.0,
                        "total_md": 5000.0,
                        "total_tvd": 3500.0,
                    }}
                }
            }
        metrics = extract_metrics_from_result(MockResult(), None)
        assert metrics["max_dls"] == 8.5
        assert metrics["total_md"] == 5000.0

    def test_extract_with_risk_registry(self):
        from skills.oil_and_gas_data_manager.risk_manager import Risk, RiskRegistry
        registry = RiskRegistry()
        registry.add_risk(Risk(probability=5, impact=5))  # Critical
        registry.add_risk(Risk(probability=3, impact=3))  # High
        registry.add_risk(Risk(probability=1, impact=1))  # Low

        class EmptyResult:
            agent_results = {}

        metrics = extract_metrics_from_result(EmptyResult(), registry)
        assert metrics["total_risks"] == 3
        assert metrics["critical_risks"] == 1
        assert metrics["high_risks"] == 1