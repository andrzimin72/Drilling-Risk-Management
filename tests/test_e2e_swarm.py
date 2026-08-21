"""
End-to-End Integration Test: Full Swarm on Russian/Metric Data.
"""
import pytest
import asyncio
from pathlib import Path
from swarms.orchestrator import OrchestratorAgent, SwarmContext

RUSSIAN_DDR = """
ЕЖСУТОЧНЫЙ ОТЧЕТ БУРЕНИЯ
Скважина: 123
Куст: 5
Текущая глубина: 3245 м
Механическая скорость: 45 м/ч
Плотность раствора: 1,18 г/см3
"""

METRIC_SURVEY_CSV = """
Глубина по стволу,Зенитный угол,Азимут
0,0,45
1000,5,46
2000,25,48
3000,85,50
3245,90,52
"""

class TestEndToEndSwarm:
    def test_e2e_russian_metric_swarm(self, tmp_path):
        """Full swarm must process Russian/Metric files without sanity errors."""
        ddr = tmp_path / "ddr.txt"
        ddr.write_text(RUSSIAN_DDR)
        
        survey = tmp_path / "survey.csv"
        survey.write_text(METRIC_SURVEY_CSV)
        
        orchestrator = OrchestratorAgent(verbose=False)
        ctx = SwarmContext(well_name="123", pad="5")
        
        # Run the async swarm
        result = asyncio.run(orchestrator.run([ddr, survey], ctx))
        
        assert result.status == "complete"
        assert result.files_processed == 2
        
        # 1. Verify Drilling Agent didn't throw false metric sanity flags
        drill_flags = result.agent_results.get("drilling", {}).get("quality_flags", [])
        assert not any("SANITY" in f for f in drill_flags), f"False sanity flags: {drill_flags}"
        
        # 2. Verify Directional Agent parsed Russian CSV headers
        dir_data = result.agent_results.get("directional", {}).get("extracted_data", {}).get("directional", {})
        stations = dir_data.get("raw_stations", [])
        assert len(stations) >= 3, "Directional agent failed to parse Russian survey headers"
        
        # 3. Verify final report was generated
        assert len(result.unified_report) > 100