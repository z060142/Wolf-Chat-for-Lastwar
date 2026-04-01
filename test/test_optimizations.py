"""
Wolf Chat Optimization Tests
Tests for the optimization improvements made in 2026-01-23
"""
import pytest
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.json_helper import safe_json_loads, safe_json_dumps, validate_json_schema
from utils.cache_manager import TTLCache
from utils.logger_config import setup_logger


class TestJSONHelper:
    """JSON Helper Utility Tests"""

    def test_valid_json(self):
        """Test parsing valid JSON"""
        result = safe_json_loads('{"key": "value"}', expected_type=dict)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        """Test parsing invalid JSON returns default"""
        result = safe_json_loads('invalid', default={})
        assert result == {}

    def test_type_mismatch(self):
        """Test type validation"""
        result = safe_json_loads('[1,2,3]', default={}, expected_type=dict)
        assert result == {}

    def test_none_input(self):
        """Test None input handling"""
        result = safe_json_loads(None, default="fallback")
        assert result == "fallback"

    def test_schema_validation_success(self):
        """Test schema validation with valid data"""
        data = {"dialogue": "test", "action": "none"}
        assert validate_json_schema(data, ["dialogue"]) == True

    def test_schema_validation_failure(self):
        """Test schema validation with missing keys"""
        data = {"dialogue": "test"}
        assert validate_json_schema(data, ["missing_key"]) == False

    def test_safe_dumps(self):
        """Test safe JSON serialization"""
        data = {"key": "value"}
        result = safe_json_dumps(data)
        assert '"key"' in result
        assert '"value"' in result


class TestCache:
    """Cache Manager Tests"""

    @pytest.mark.asyncio
    async def test_cache_set_get(self):
        """Test basic cache set and get"""
        cache = TTLCache(maxsize=10, ttl=300)
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_cache_expiry(self):
        """Test cache TTL expiration"""
        cache = TTLCache(maxsize=10, ttl=1)  # 1 second TTL
        await cache.set("key1", "value1")
        await asyncio.sleep(2)  # Wait for expiry
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """Test LRU eviction when max size reached"""
        cache = TTLCache(maxsize=2, ttl=300)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")  # Should evict key1

        # key1 should be evicted
        result1 = await cache.get("key1")
        assert result1 is None

        # key2 and key3 should still exist
        result2 = await cache.get("key2")
        result3 = await cache.get("key3")
        assert result2 == "value2"
        assert result3 == "value3"

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """Test cache clearing"""
        cache = TTLCache(maxsize=10, ttl=300)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()

        result1 = await cache.get("key1")
        result2 = await cache.get("key2")
        assert result1 is None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics"""
        cache = TTLCache(maxsize=10, ttl=300)
        await cache.set("key1", "value1")
        stats = await cache.get_stats()

        assert stats["size"] == 1
        assert stats["valid"] == 1
        assert stats["maxsize"] == 10
        assert stats["ttl"] == 300


class TestLogger:
    """Logger Configuration Tests"""

    def test_logger_setup(self):
        """Test logger initialization"""
        import tempfile
        import os

        # Create temp log file
        temp_log = os.path.join(tempfile.gettempdir(), "test_wolf_chat.log")

        logger = setup_logger("test_logger", log_file=temp_log)
        assert logger.name == "test_logger"

        # Test logging
        logger.info("Test message")

        # Check log file exists
        assert os.path.exists(temp_log)

        # Cleanup
        if os.path.exists(temp_log):
            os.remove(temp_log)

    def test_logger_no_duplicate_handlers(self):
        """Test that calling setup_logger twice doesn't add duplicate handlers"""
        logger1 = setup_logger("test_dup")
        handler_count_1 = len(logger1.handlers)

        logger2 = setup_logger("test_dup")  # Same name
        handler_count_2 = len(logger2.handlers)

        assert handler_count_1 == handler_count_2


class TestAppState:
    """AppState Tests"""

    @pytest.mark.asyncio
    async def test_app_state_history(self):
        """Test conversation history management"""
        from utils.app_state import AppState

        state = AppState()

        # Add messages
        await state.add_to_history({"role": "user", "content": "Hello"})
        await state.add_to_history({"role": "assistant", "content": "Hi"})

        # Get recent history
        history = await state.get_recent_history(count=10)
        assert len(history) == 2
        assert history[0]["content"] == "Hello"

        # Clear history
        await state.clear_history()
        history = await state.get_recent_history(count=10)
        assert len(history) == 0

    def test_app_state_control_flags(self):
        """Test pause/resume/shutdown flags"""
        from utils.app_state import AppState

        state = AppState()

        # Test pause/resume
        assert state.script_paused == False
        state.pause()
        assert state.script_paused == True
        state.resume()
        assert state.script_paused == False

        # Test shutdown
        assert state.shutdown_requested == False
        state.request_shutdown()
        assert state.shutdown_requested == True


class TestQueueBridge:
    """Queue Bridge Tests"""

    @pytest.mark.asyncio
    async def test_queue_put_get(self):
        """Test basic queue operations"""
        from utils.queue_bridge import AsyncQueueBridge

        queue = AsyncQueueBridge("test_queue")
        await queue.put("test_data")
        result = await queue.get()
        assert result == "test_data"

    @pytest.mark.asyncio
    async def test_queue_timeout(self):
        """Test queue timeout handling"""
        from utils.queue_bridge import AsyncQueueBridge

        queue = AsyncQueueBridge("test_queue")

        # Test get timeout
        with pytest.raises(asyncio.TimeoutError):
            await queue.get(timeout=0.1)

    @pytest.mark.asyncio
    async def test_queue_size(self):
        """Test queue size tracking"""
        from utils.queue_bridge import AsyncQueueBridge

        queue = AsyncQueueBridge("test_queue", maxsize=10)
        await queue.put("item1")
        await queue.put("item2")

        assert queue.qsize() == 2
        assert not queue.empty()

        await queue.get()
        await queue.get()

        assert queue.empty()


# Integration tests
class TestIntegration:
    """Integration tests for optimization components"""

    @pytest.mark.asyncio
    async def test_json_with_cache(self):
        """Test JSON parsing with caching"""
        from utils.cache_manager import TTLCache

        cache = TTLCache(maxsize=10, ttl=300)

        # Simulate cached JSON parse result
        json_str = '{"key": "value"}'
        parsed = safe_json_loads(json_str, expected_type=dict)
        await cache.set(f"json:{json_str}", parsed)

        # Retrieve from cache
        cached_result = await cache.get(f"json:{json_str}")
        assert cached_result == parsed


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
