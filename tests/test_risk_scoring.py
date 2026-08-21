"""
Tests for the RiskScoringEngine — verifies risks are correctly
generated from agent results.
"""
import pytest
from skills.oil_and_gas_data_manager.risk_manager import (
    RiskScoringEngine, RiskLevel, RiskCategory
)


def _make_swarm_result(agent_results: dict, quality_flags=None, cross_flags=None):
    """Helper to create a mock SwarmResult."""
    class MockSwarmResult:
        def __init__(self, agent_results, quality_flags, cross_flags):
            self.agent_results = agent_results
            self.quality_flags = quality_flags or []
            self.cross_domain_flags = cross_flags or []
    return MockSwarmResult(agent_results, quality_flags, cross_flags)


class TestDrillingRiskAnalysis:
    def test_high_npt_generates_risk(self):
        engine = RiskScoringEngine(language="ru")
        result = _make_swarm_result({
            "drilling": {
                "extracted_data": {"drilling": {"npt_hours": 15.0, "npt_events": [
                    {"description": "Pump failure", "duration_hrs": 15}
                ]}},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_drilling(result.agent_results["drilling"])
        assert len(risks) >= 1
        assert any(r.category == RiskCategory.OPERATIONAL for r in risks)

    def test_moderate_npt_generates_risk(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "drilling": {
                "extracted_data": {"drilling": {"npt_hours": 7.0, "npt_events": []}},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_drilling(result.agent_results["drilling"])
        assert len(risks) >= 1

    def test_low_npt_no_risk(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "drilling": {
                "extracted_data": {"drilling": {"npt_hours": 2.0, "npt_events": []}},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_drilling(result.agent_results["drilling"])
        assert len(risks) == 0

    def test_mud_weight_sanity_failure(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "drilling": {
                "extracted_data": {"drilling": {}},
                "quality_flags": ["SANITY: mud_weight outside expected range (value=25.0)"],
            }
        })
        risks = engine.analyze_drilling(result.agent_results["drilling"])
        assert any(r.category == RiskCategory.TECHNICAL for r in risks)


class TestDirectionalRiskAnalysis:
    def test_high_dls_generates_critical_risk(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "directional": {
                "extracted_data": {"directional": {"max_dls": 12.5}},
                "quality_flags": ["HIGH_DLS: 12.5°/100ft at 3000 ft MD"],
            }
        })
        risks = engine.analyze_directional(result.agent_results["directional"])
        assert len(risks) >= 1
        assert risks[0].risk_level == RiskLevel.CRITICAL  # P=4, I=4
        assert "stuck pipe" in risks[0].description_en.lower()

    def test_inclination_jump_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "directional": {
                "extracted_data": {"directional": {}},
                "quality_flags": ["INC_JUMP: 8.5° change at 1500 ft MD"],
            }
        })
        risks = engine.analyze_directional(result.agent_results["directional"])
        assert any("inclination" in r.title_en.lower() or "зенит" in r.title_ru.lower()
                   for r in risks)

    def test_survey_gap_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "directional": {
                "extracted_data": {"directional": {}},
                "quality_flags": ["SURVEY_GAP: 150 ft gap at 2000 ft MD"],
            }
        })
        risks = engine.analyze_directional(result.agent_results["directional"])
        assert len(risks) >= 1


class TestHSERiskAnalysis:
    def test_fatality_generates_critical_risk(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "hse": {
                "extracted_data": {"hse": {
                    "incident_counts": {"fatality": 1, "lti": 0},
                    "incidents": [],
                    "recurring_patterns": [],
                }},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_hse(result.agent_results["hse"])
        assert len(risks) >= 1
        assert risks[0].risk_level == RiskLevel.CRITICAL  # P=5, I=5
        assert risks[0].category == RiskCategory.HSE

    def test_lti_generates_high_risk(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "hse": {
                "extracted_data": {"hse": {
                    "incident_counts": {"fatality": 0, "lti": 2},
                    "incidents": [],
                    "recurring_patterns": [],
                }},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_hse(result.agent_results["hse"])
        assert any(r.risk_level == RiskLevel.CRITICAL for r in risks)  # P=4, I=5 = 20

    def test_sif_potential_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "hse": {
                "extracted_data": {"hse": {
                    "incident_counts": {},
                    "incidents": [
                        {"severity": "near_miss", "sif_potential": True,
                         "description": "Dropped object from height"}
                    ],
                    "recurring_patterns": [],
                }},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_hse(result.agent_results["hse"])
        assert any("SIF" in r.title_en for r in risks)

    def test_recurring_pattern_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "hse": {
                "extracted_data": {"hse": {
                    "incident_counts": {},
                    "incidents": [],
                    "recurring_patterns": [
                        {"pattern": "stuck pipe", "occurrence_count": 3,
                         "recommendation": "Review stuck pipe procedures"}
                    ],
                }},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_hse(result.agent_results["hse"])
        assert any("stuck pipe" in r.title_en.lower() for r in risks)


class TestLogsRiskAnalysis:
    def test_no_pay_zones_identified(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "logs": {
                "extracted_data": {"logs": {
                    "pay_zone_count": 0,
                    "curves": [{"mnemonic": "GR"}, {"mnemonic": "RT"}],
                }},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_logs(result.agent_results["logs"])
        assert any(r.category == RiskCategory.GEOLOGICAL for r in risks)

    def test_missing_gr_curve_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result({
            "logs": {
                "extracted_data": {"logs": {
                    "pay_zone_count": 1,
                    "curves": [{"mnemonic": "RT"}],  # No GR
                }},
                "quality_flags": [],
            }
        })
        risks = engine.analyze_logs(result.agent_results["logs"])
        assert any("GR" in r.title_en for r in risks)


class TestCrossDomainRiskAnalysis:
    def test_depth_mismatch_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result(
            agent_results={},
            cross_flags=["CROSS_DOMAIN: LAS max depth 9500 ft vs drilling 8000 ft (>10% mismatch)"]
        )
        risks = engine.analyze_quality_flags(result)
        assert len(risks) >= 1
        assert any("depth" in r.title_en.lower() for r in risks)

    def test_under_stimulation_flagged(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result(
            agent_results={},
            cross_flags=["CROSS_DOMAIN: 10 frac stages vs 25 log-identified pay zones — possible under-stimulation"]
        )
        risks = engine.analyze_quality_flags(result)
        assert any("stimulation" in r.title_en.lower() for r in risks)


class TestRAGWarningAnalysis:
    def test_predictive_risk_from_rag(self):
        engine = RiskScoringEngine()
        result = _make_swarm_result(
            agent_results={},
            quality_flags=[
                "PREDICTIVE_RISK: Historical data on pad 'Куст 5' shows Well 122 experienced 24 hrs NPT at 3100m"
            ]
        )
        risks = engine.analyze_rag_warnings(result)
        assert len(risks) >= 1
        assert risks[0].category == RiskCategory.GEOLOGICAL
        assert risks[0].risk_level == RiskLevel.CRITICAL  # P=4, I=4


class TestGenerateAllRisks:
    def test_full_pipeline_generates_risks(self):
        engine = RiskScoringEngine(language="ru")
        result = _make_swarm_result(
            agent_results={
                "drilling": {
                    "extracted_data": {"drilling": {"npt_hours": 12.0, "npt_events": []}},
                    "quality_flags": [],
                },
                "directional": {
                    "extracted_data": {"directional": {"max_dls": 10.0}},
                    "quality_flags": ["HIGH_DLS: 10.0°/100ft"],
                },
                "hse": {
                    "extracted_data": {"hse": {
                        "incident_counts": {"lti": 1},
                        "incidents": [],
                        "recurring_patterns": [],
                    }},
                    "quality_flags": [],
                },
            },
            quality_flags=["PREDICTIVE_RISK: Historical stuck pipe at 3000m"],
            cross_flags=["CROSS_DOMAIN: depth mismatch"],
        )
        all_risks = engine.generate_all_risks(result)
        assert len(all_risks) >= 5  # At least one from each domain

        # Verify categories are diverse
        categories = {r.category for r in all_risks}
        assert RiskCategory.OPERATIONAL in categories
        assert RiskCategory.TECHNICAL in categories
        assert RiskCategory.HSE in categories