"""
Tests for Architectural Resilience (Caching & Retries).
"""
import pytest
import time
from pathlib import Path
# Adjust import path based on where you saved utils.py
from skills.oil_and_gas_data_manager.utils import FileCache, retry_on_io_error 

class TestFileCache:
    def test_cache_saves_and_retrieves(self, tmp_path):
        cache = FileCache(tmp_path / "cache")
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        
        cache.set(test_file, "extract", {"data": "parsed"})
        result = cache.get(test_file, "extract")
        
        assert result == {"data": "parsed"}

    def test_cache_invalidates_on_file_change(self, tmp_path):
        cache = FileCache(tmp_path / "cache")
        test_file = tmp_path / "test.txt"
        test_file.write_text("v1")
        cache.set(test_file, "extract", {"data": "v1"})
        
        # Modify file (ensure mtime changes)
        time.sleep(0.1) 
        test_file.write_text("v2")
        
        result = cache.get(test_file, "extract")
        assert result is None # Cache must be invalidated

class TestRetryLogic:
    def test_retry_succeeds_after_transient_error(self):
        call_count = 0
        
        @retry_on_io_error(max_retries=3, base_delay=0.01)
        def flaky_network_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("Network drive disconnected")
            return "success"
            
        result = flaky_network_call()
        assert result == "success"
        assert call_count == 3

    def test_retry_fails_after_max_attempts(self):
        @retry_on_io_error(max_retries=2, base_delay=0.01)
        def permanent_failure():
            raise OSError("Drive offline")
            
        with pytest.raises(OSError):
            permanent_failure()