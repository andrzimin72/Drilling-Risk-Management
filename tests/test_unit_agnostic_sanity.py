"""
Tests for Unit-Agnostic Sanity Checks.
"""
import pytest
from skills.oil_and_gas_data_manager.skill import run_sanity_checks

class TestUnitAgnosticSanity:
    def test_metric_mud_weight_passes(self):
        """1.18 sg is normal mud weight. Must NOT flag."""
        extracted = {"drilling": {"mud_weight_sg": 1.18}}
        flags = run_sanity_checks(extracted)
        assert not any("mud_weight" in f.lower() for f in flags)

    def test_metric_rop_passes(self):
        """45 m/hr is normal ROP. Must NOT flag."""
        extracted = {"drilling": {"rop_m_hr": 45.0}}
        flags = run_sanity_checks(extracted)
        assert not any("rop" in f.lower() for f in flags)

    def test_impossible_metric_depth_flagged(self):
        """25,000 meters is impossible. Must flag."""
        extracted = {"drilling": {"depth_m": 25000.0}}
        flags = run_sanity_checks(extracted)
        assert any("depth" in f.lower() for f in flags)

    def test_imperial_data_still_validated(self):
        """Ensure we didn't break Imperial sanity checks."""
        extracted = {"drilling": {"mud_weight_ppg": 25.0}} # Impossible
        flags = run_sanity_checks(extracted)
        assert any("mud_weight" in f.lower() for f in flags)

    def test_mixed_units_dont_cross_contaminate(self):
        """If a file somehow has both, both should be evaluated independently."""
        extracted = {"drilling": {"mud_weight_ppg": 10.5, "mud_weight_sg": 1.18}}
        flags = run_sanity_checks(extracted)
        assert not any("sanity" in f.lower() for f in flags)