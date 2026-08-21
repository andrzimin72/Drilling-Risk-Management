"""
Tests for Configurable Petrophysics and Unit-Agnostic LAS parsing.
"""
import pytest
from pathlib import Path
from skills.oil_and_gas_data_manager.parsers.las_parser import LasParser

# Synthetic Metric LAS file
METRIC_LAS = """~Version
VERS. 2.0
WRAP. NO
~Well
WELL. SIBERIAN WELL 1
STRT.M 2000.0
STOP.M 2003.0
STEP.M 1.0
NULL. -999.25
~Curve
DEPT.M
GR.GAPI
RT.OHMM
~ASCII
2000.0 80.0 5.0
2001.0 70.0 15.0
2002.0 50.0 25.0
2003.0 85.0 4.0
"""

class TestConfigurablePetrophysics:
    def test_metric_las_depth_unit_detection(self, tmp_path):
        """Parser must detect 'm' from the LAS header."""
        las_file = tmp_path / "metric.las"
        las_file.write_text(METRIC_LAS)
        
        parser = LasParser()
        extracted, _, _ = parser.extract_structured(las_file)
        
        assert extracted["logs"]["depth_unit"] == "m"

    def test_custom_cutoffs_identify_correct_pay(self, tmp_path):
        """Custom cutoffs (GR < 60, RT > 10) should only find the 3rd row as pay."""
        las_file = tmp_path / "metric.las"
        las_file.write_text(METRIC_LAS)
        
        # Western Siberia clastic cutoffs
        parser = LasParser(gr_cutoff=60.0, rt_cutoff=10.0)
        extracted, _, _ = parser.extract_structured(las_file)
        pay = extracted["logs"]["pay_intervals"]
        
        assert len(pay) == 1
        assert pay[0]["top"] == 2002.0
        assert pay[0]["net_pay"] == 1.0
        assert pay[0]["depth_unit"] == "m"

    def test_default_cutoffs_still_work(self, tmp_path):
        """Default cutoffs (GR < 75, RT > 10) should find rows 2 and 3 as pay."""
        las_file = tmp_path / "metric.las"
        las_file.write_text(METRIC_LAS)
        
        parser = LasParser() # Defaults
        extracted, _, _ = parser.extract_structured(las_file)
        pay = extracted["logs"]["pay_intervals"]
        
        # Row 2 (GR=70, RT=15) and Row 3 (GR=50, RT=25) are both pay
        assert len(pay) == 1 # Contiguous interval
        assert pay[0]["top"] == 2001.0
        assert pay[0]["base"] == 2002.0
        assert pay[0]["net_pay"] == 2.0 # 2 meters of net pay