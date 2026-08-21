"""
Tests for Pydantic Schema Enforcement.
"""
import pytest
from skills.oil_and_gas_data_manager.schemas.extraction_schema import (
    DrillingDataSchema, LogsDataSchema
)

class TestSchemaEnforcement:
    def test_drilling_schema_coerces_strings_to_floats(self):
        """Parsers often return strings. Schema must coerce to float."""
        raw = {"rop_m_hr": "45.5", "mud_weight_sg": "1.18", "current_depth_m": "3245"}
        validated = DrillingDataSchema.model_validate(raw)
        
        assert validated.rop_m_hr == 45.5
        assert validated.mud_weight_sg == 1.18
        assert validated.current_depth_m == 3245.0

    def test_logs_schema_handles_metric_pay_intervals(self):
        """Schema must accept metric depth units."""
        raw = {
            "depth_unit": "m",
            "total_net_pay": 15.5,
            "pay_intervals": [
                {"top": 2000.0, "base": 2010.0, "net_pay": 10.0, "depth_unit": "m"}
            ]
        }
        validated = LogsDataSchema.model_validate(raw)
        
        assert validated.depth_unit == "m"
        assert len(validated.pay_intervals) == 1
        assert validated.pay_intervals[0].depth_unit == "m"

    def test_schema_excludes_none_values(self):
        """model_dump(exclude_none=True) must clean the payload for the ReportAgent."""
        raw = {"rop_m_hr": 45.5, "mud_weight_sg": None}
        validated = DrillingDataSchema.model_validate(raw)
        dumped = validated.model_dump(exclude_none=True)
        
        assert "rop_m_hr" in dumped
        assert "mud_weight_sg" not in dumped
