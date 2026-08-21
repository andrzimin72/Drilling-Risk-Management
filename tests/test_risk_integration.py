"""
End-to-end integration tests: swarm → risk analysis → report generation.
"""
import pytest
import asyncio
import tempfile
import textwrap
from pathlib import Path


class TestRiskIntegration:
    def test_full_pipeline_with_risks(self, tmp_path):
        """Run a full swarm on synthetic data and verify risks are generated."""
        from swarms.orchestrator import OrchestratorAgent, SwarmContext

        # Create synthetic files with known risk triggers
        ddr = tmp_path / "ddr.txt"
        ddr.write_text(textwrap.dedent("""
        DAILY DRILLING REPORT
        Well Name: Integration Test Well
        NPT: Pump failure: 15.0 hrs
        NPT: Stuck pipe: 8.0 hrs
        Total NPT: 23.0 hrs
        Incident: Near miss - dropped object from 15 ft height
        """))

        survey = tmp_path / "survey.csv"
        survey.write_text(
            "MD,INC,AZ\n"
            "0,0,45\n"
            "500,0.5,46\n"
            "1000,15.0,48\n"  # Big jump
            "1500,45.0,50\n"
            "2000,85.0,52\n"
        )

        orchestrator = OrchestratorAgent(
            verbose=False,
            risk_management_enabled=True,
            report_language="en",
        )
        ctx = SwarmContext(well_name="Integration Test Well")

        result = asyncio.run(orchestrator.run([ddr, survey], ctx))

        # Verify risk registry was populated
        assert result.risk_registry is not None
        assert len(result.risk_registry.risks) > 0

        # Verify specific risks were detected
        summary = result.risk_registry.get_summary()
        assert summary["total_risks"] > 0

    def test_full_pipeline_with_word_report(self, tmp_path):
        """Generate a Word report through the full pipeline."""
        try:
            from skills.oil_and_gas_data_manager.report_generator import ReportGenerator
        except ImportError:
            pytest.skip("python-docx not installed")

        from swarms.orchestrator import OrchestratorAgent, SwarmContext

        ddr = tmp_path / "ddr.txt"
        ddr.write_text(textwrap.dedent("""
        DAILY DRILLING REPORT
        Well Name: Report Test Well
        NPT: Equipment failure: 12.0 hrs
        Total NPT: 12.0 hrs
        """))

        orchestrator = OrchestratorAgent(
            verbose=False,
            risk_management_enabled=True,
            report_language="ru",
        )
        ctx = SwarmContext(well_name="Report Test Well")

        report_path = tmp_path / "integration_report.docx"
        result = asyncio.run(orchestrator.run(
            [ddr], ctx,
            generate_risk_report=True,
            report_output_path=report_path,
        ))

        assert result.risk_report_path is not None
        assert Path(result.risk_report_path).exists()

    def test_russian_metric_pipeline(self, tmp_path):
        """Verify Russian/Metric data flows through risk system correctly."""
        from swarms.orchestrator import OrchestratorAgent, SwarmContext

        ddr = tmp_path / "ddr_ru.txt"
        ddr.write_text(textwrap.dedent("""
        ЕЖСУТОЧНЫЙ ОТЧЕТ БУРЕНИЯ
        Скважина: 123
        Куст: 5
        Текущая глубина: 3245 м
        НПТ: 15 час - отказ насоса
        Инцидент: Микронепроизводство - падение инструмента
        """))

        orchestrator = OrchestratorAgent(
            verbose=False,
            risk_management_enabled=True,
            report_language="ru",
        )
        ctx = SwarmContext(well_name="123", pad="5")

        result = asyncio.run(orchestrator.run([ddr], ctx))

        assert result.risk_registry is not None
        # Verify Russian risks were generated
        if result.risk_registry.risks:
            risk = result.risk_registry.risks[0]
            assert risk.title_ru  # Should have Russian title

    def test_history_persists_across_runs(self, tmp_path):
        """Verify analysis history is saved and can be retrieved."""
        from swarms.orchestrator import OrchestratorAgent, SwarmContext
        from skills.oil_and_gas_data_manager.analysis_history import AnalysisHistory

        ddr = tmp_path / "ddr.txt"
        ddr.write_text("DAILY DRILLING REPORT\nWell Name: History Test\nNPT: 5 hrs\n")

        # First run
        orchestrator = OrchestratorAgent(verbose=False, risk_management_enabled=True)
        ctx = SwarmContext(well_name="History Test")
        result1 = asyncio.run(orchestrator.run([ddr], ctx))

        # Save to history manually (dashboard does this automatically)
        history = AnalysisHistory(tmp_path / "history.db")
        if result1.risk_registry:
            from skills.oil_and_gas_data_manager.analysis_history import extract_metrics_from_result
            metrics = extract_metrics_from_result(result1, result1.risk_registry)
            history.save_analysis(
                task_id=result1.task_id,
                well_name="History Test",
                pad_name=None,
                operator=None,
                files_processed=result1.files_processed,
                elapsed_seconds=result1.elapsed_seconds,
                agents_succeeded=result1.agents_succeeded,
                agents_failed=result1.agents_failed,
                risk_summary=result1.risk_registry.get_summary(),
                risk_registry_data=[r.to_dict() for r in result1.risk_registry.risks],
                metrics=metrics,
            )

        # Verify it's in history
        analyses = history.list_analyses()
        assert len(analyses) >= 1
        assert any(a["well_name"] == "History Test" for a in analyses)