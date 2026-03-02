"""Tests for statusline.py — unit tests + smoke tests."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path so we can import statusline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Disable colors for deterministic test output
os.environ["NO_COLOR"] = "1"

import statusline


# ============================================
# Unit Tests — pure function input/output
# ============================================


class TestFormatTokenCount:
    def test_millions(self):
        assert statusline.format_token_count(1500000) == "1.5M"

    def test_thousands(self):
        assert statusline.format_token_count(1000) == "1.0K"
        assert statusline.format_token_count(45000) == "45.0K"

    def test_below_thousand(self):
        assert statusline.format_token_count(500) == "500"
        assert statusline.format_token_count(0) == "0"


class TestFormatTokenCountShort:
    def test_large_millions(self):
        assert statusline.format_token_count_short(200000000) == "200M"

    def test_small_millions(self):
        assert statusline.format_token_count_short(14000000) == "14.0M"
        assert statusline.format_token_count_short(1500000) == "1.5M"

    def test_large_thousands(self):
        assert statusline.format_token_count_short(332000) == "332K"
        assert statusline.format_token_count_short(500000) == "500K"

    def test_small_thousands(self):
        assert statusline.format_token_count_short(14000) == "14.0K"
        assert statusline.format_token_count_short(99500) == "99.5K"

    def test_below_thousand(self):
        assert statusline.format_token_count_short(999) == "999"
        assert statusline.format_token_count_short(0) == "0"


class TestShortenModelName:
    def test_normal_mode(self):
        assert statusline.shorten_model_name("Claude Opus 4.6") == "Opus 4.6"
        assert statusline.shorten_model_name("Claude Sonnet 4") == "Sonnet 4"

    def test_context_suffix_stripped(self):
        assert statusline.shorten_model_name("Claude Sonnet 4.6 (1M context)") == "Sonnet 4.6"
        assert statusline.shorten_model_name("Sonnet 4.6 (200k context)") == "Sonnet 4.6"

    def test_version_before_family(self):
        assert statusline.shorten_model_name("Claude 3.5 Sonnet") == "Sonnet 3.5"
        assert statusline.shorten_model_name("3.5 Haiku") == "Haiku 3.5"

    def test_tight_mode(self):
        assert statusline.shorten_model_name("Claude Opus 4.6", tight=True) == "Op4.6"
        assert statusline.shorten_model_name("Claude Sonnet 4", tight=True) == "Son4"
        assert statusline.shorten_model_name("Claude 3.5 Haiku", tight=True) == "Hai3.5"
        assert statusline.shorten_model_name("Claude Sonnet 4.6 (1M context)", tight=True) == "Son4.6"


class TestTruncateText:
    def test_short_text(self):
        assert statusline.truncate_text("hello", 10) == "hello"

    def test_exact_length(self):
        assert statusline.truncate_text("hello", 5) == "hello"

    def test_long_text(self):
        assert statusline.truncate_text("hello world", 8) == "hello..."

    def test_max_len_3_or_less(self):
        assert statusline.truncate_text("hello", 3) == "hel"
        assert statusline.truncate_text("hello", 1) == "h"


class TestGetDisplayMode:
    def test_full(self):
        assert statusline.get_display_mode(68) == "full"
        assert statusline.get_display_mode(120) == "full"
        assert statusline.get_display_mode(55) == "full"

    def test_compact(self):
        assert statusline.get_display_mode(35) == "compact"
        assert statusline.get_display_mode(54) == "compact"

    def test_tight(self):
        assert statusline.get_display_mode(34) == "tight"
        assert statusline.get_display_mode(10) == "tight"


class TestGetDisplayWidth:
    def test_ascii(self):
        assert statusline.get_display_width("hello") == 5

    def test_cjk(self):
        # CJK characters are width 2
        assert statusline.get_display_width("\u6d4b\u8bd5") == 4  # two CJK chars

    def test_ansi_ignored(self):
        assert statusline.get_display_width("\033[1;91mhello\033[0m") == 5

    def test_empty(self):
        assert statusline.get_display_width("") == 0


class TestStripAnsi:
    def test_strips_color(self):
        assert statusline.strip_ansi("\033[1;91mred\033[0m") == "red"

    def test_no_ansi(self):
        assert statusline.strip_ansi("plain") == "plain"

    def test_multiple_codes(self):
        assert statusline.strip_ansi("\033[1m\033[91mbold red\033[0m") == "bold red"


class TestGetProgressBar:
    def test_zero_percent(self):
        bar = statusline.get_progress_bar(0, width=10)
        clean = statusline.strip_ansi(bar)
        assert len(clean) == 10
        assert clean.count("█") == 0

    def test_fifty_percent(self):
        bar = statusline.get_progress_bar(50, width=10)
        clean = statusline.strip_ansi(bar)
        assert clean.count("█") == 5

    def test_hundred_percent(self):
        bar = statusline.get_progress_bar(100, width=10)
        clean = statusline.strip_ansi(bar)
        assert clean.count("█") == 10

    def test_fraction_segment(self):
        # 49% of 20 = 9.8 -> 9 filled + 1 dim + 10 empty = 20
        bar = statusline.get_progress_bar(49, width=20)
        clean = statusline.strip_ansi(bar)
        assert len(clean) == 20
        assert clean.count("█") == 10  # 9 bright + 1 dim
        assert clean.count("▒") == 10

    def test_no_fraction_at_zero(self):
        bar = statusline.get_progress_bar(0, width=20)
        clean = statusline.strip_ansi(bar)
        assert clean.count("█") == 0
        assert clean.count("▒") == 20

    def test_no_fraction_at_hundred(self):
        bar = statusline.get_progress_bar(100, width=20)
        clean = statusline.strip_ansi(bar)
        assert clean.count("█") == 20
        assert clean.count("▒") == 0

    def test_fraction_uses_dim_color(self):
        """Verify fractional segment uses dim color when colors are enabled"""
        import os
        saved = os.environ.pop('NO_COLOR', None)
        try:
            bar = statusline.get_progress_bar(49, width=20)
            assert '\033[32m' in bar  # DIM_GREEN (non-bold)
        finally:
            if saved is not None:
                os.environ['NO_COLOR'] = saved

    def test_total_width_consistent(self):
        for pct in [0, 10, 25, 33, 49, 50, 75, 80, 90, 99, 100]:
            bar = statusline.get_progress_bar(pct, width=20)
            clean = statusline.strip_ansi(bar)
            assert len(clean) == 20, f"Width mismatch at {pct}%: got {len(clean)}"


class TestCreateSparkline:
    def test_empty(self):
        assert statusline.create_sparkline([]) == ""

    def test_all_zeros(self):
        result = statusline.create_sparkline([0, 0, 0], width=3)
        clean = statusline.strip_ansi(result)
        assert len(clean) == 3

    def test_all_same_nonzero(self):
        result = statusline.create_sparkline([5, 5, 5], width=3)
        clean = statusline.strip_ansi(result)
        assert len(clean) == 3

    def test_varying_values(self):
        result = statusline.create_sparkline([1, 5, 10], width=3)
        clean = statusline.strip_ansi(result)
        assert len(clean) == 3


class TestGetPercentageColor:
    def test_green_below_80(self):
        result = statusline.get_percentage_color(79)
        assert result == statusline.Colors.BRIGHT_GREEN

    def test_yellow_at_80(self):
        result = statusline.get_percentage_color(80)
        assert result == statusline.Colors.BRIGHT_YELLOW

    def test_yellow_at_89(self):
        result = statusline.get_percentage_color(89)
        assert result == statusline.Colors.BRIGHT_YELLOW

    def test_red_at_90(self):
        result = statusline.get_percentage_color(90)
        assert result == "\033[1;91m"


class TestGetPercentageColorDim:
    def test_dim_green_below_80(self):
        result = statusline.get_percentage_color_dim(79)
        assert result == statusline.Colors.DIM_GREEN

    def test_dim_yellow_at_80(self):
        result = statusline.get_percentage_color_dim(80)
        assert result == statusline.Colors.DIM_YELLOW

    def test_dim_red_at_90(self):
        result = statusline.get_percentage_color_dim(90)
        assert result == statusline.Colors.DIM_RED

    def test_dim_differs_from_bright_with_color(self):
        """Verify dim colors differ from bright when colors are enabled"""
        import os
        saved = os.environ.pop('NO_COLOR', None)
        try:
            assert statusline.get_percentage_color_dim(50) != statusline.get_percentage_color(50)
        finally:
            if saved is not None:
                os.environ['NO_COLOR'] = saved


class TestFormatCost:
    def test_very_small(self):
        assert statusline.format_cost(0.003) == "$0.0030"

    def test_under_one(self):
        assert statusline.format_cost(0.03) == "$0.030"
        assert statusline.format_cost(0.5) == "$0.500"

    def test_over_one(self):
        assert statusline.format_cost(1.50) == "$1.50"
        assert statusline.format_cost(12.34) == "$12.34"


class TestCalculateCost:
    def test_opus_pricing(self):
        cost = statusline.calculate_cost(
            input_tokens=1000000, output_tokens=100000,
            cache_creation=0, cache_read=0,
            model_name="Opus 4"
        )
        # Input: 1M * $15/M = $15, Output: 0.1M * $75/M = $7.5
        expected = 15.0 + 7.5
        assert abs(cost - expected) < 0.001

    def test_sonnet_pricing(self):
        cost = statusline.calculate_cost(
            input_tokens=1000000, output_tokens=100000,
            cache_creation=0, cache_read=0,
            model_name="Sonnet 4"
        )
        # Input: 1M * $3/M = $3, Output: 0.1M * $15/M = $1.5
        expected = 3.0 + 1.5
        assert abs(cost - expected) < 0.001

    def test_haiku_pricing(self):
        cost = statusline.calculate_cost(
            input_tokens=1000000, output_tokens=100000,
            cache_creation=0, cache_read=0,
            model_name="Haiku"
        )
        # Input: 1M * $1/M = $1, Output: 0.1M * $5/M = $0.5
        expected = 1.0 + 0.5
        assert abs(cost - expected) < 0.001

    def test_cache_tokens(self):
        cost = statusline.calculate_cost(
            input_tokens=0, output_tokens=0,
            cache_creation=1000000, cache_read=1000000,
            model_name="Opus 4"
        )
        # Cache write: 1M * $18.75/M, Cache read: 1M * $1.50/M
        expected = 18.75 + 1.50
        assert abs(cost - expected) < 0.001

    def test_model_id_detection(self):
        cost = statusline.calculate_cost(
            input_tokens=1000000, output_tokens=0,
            cache_creation=0, cache_read=0,
            model_name="Unknown", model_id="claude-sonnet-4-6"
        )
        # Should detect "sonnet" in model_id
        assert abs(cost - 3.0) < 0.001


# ============================================
# Smoke Tests — subprocess end-to-end
# ============================================

STATUSLINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "statusline.py"
)


class TestSmoke:
    def _run(self, input_data):
        return subprocess.run(
            [sys.executable, STATUSLINE_PATH],
            input=input_data,
            capture_output=True, text=True,
            timeout=10,
        )

    def _assert_output(self, result):
        """Common assertions: exit 0, meaningful stdout, no stderr errors."""
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 20, "stdout is suspiciously empty"
        assert "AttributeError" not in result.stderr
        assert "NoneType" not in result.stderr

    def test_200k_context(self):
        data = json.dumps({
            "model": {"display_name": "Opus 4.6"},
            "context_window": {
                "context_window_size": 200000,
                "used_percentage": 30,
            },
        })
        result = self._run(data)
        self._assert_output(result)

    def test_1m_context(self):
        data = json.dumps({
            "model": {"display_name": "Sonnet 4"},
            "context_window": {
                "context_window_size": 1000000,
                "used_percentage": 50,
            },
        })
        result = self._run(data)
        self._assert_output(result)

    def test_empty_input(self):
        result = self._run("")
        # Should not crash (empty input is valid — shows default state)
        assert result.returncode == 0

    def test_minimal_input(self):
        data = json.dumps({"model": {"display_name": "Opus 4.6"}})
        result = self._run(data)
        self._assert_output(result)

    def test_exceeds_200k(self):
        data = json.dumps({
            "model": {"display_name": "Opus 4.6"},
            "context_window": {
                "context_window_size": 200000,
                "used_percentage": 85,
                "exceeds_200k_tokens": True,
            },
        })
        result = self._run(data)
        self._assert_output(result)

    def test_null_current_usage(self):
        """Regression: current_usage=null caused AttributeError (session start state)."""
        data = json.dumps({
            "session_id": "test-null-usage",
            "transcript_path": "/tmp/test.jsonl",
            "cwd": "/tmp",
            "model": {"id": "claude-sonnet-4-6", "display_name": "Sonnet 4.6"},
            "workspace": {"current_dir": "/tmp", "project_dir": "/tmp", "added_dirs": []},
            "version": "2.1.47",
            "output_style": {"name": "default"},
            "cost": {
                "total_cost_usd": 0,
                "total_duration_ms": 1800,
                "total_api_duration_ms": 0,
                "total_lines_added": 0,
                "total_lines_removed": 0,
            },
            "context_window": {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "context_window_size": 200000,
                "current_usage": None,
                "used_percentage": None,
                "remaining_percentage": None,
            },
            "exceeds_200k_tokens": False,
        })
        result = self._run(data)
        self._assert_output(result)

    def test_no_used_percentage_uses_200k_denominator(self):
        """Regression: fallback display denominator must use context_window_size (200K), not compaction_threshold (160K).

        Verifies that /200K (not /160K) appears in the statusline when used_percentage is absent.
        """
        data = json.dumps({
            "model": {"id": "claude-sonnet-4-6", "display_name": "Sonnet 4.6"},
            "context_window": {
                "context_window_size": 200000,
                "current_usage": None,
                "used_percentage": None,
                "remaining_percentage": None,
            },
        })
        result = self._run(data)
        self._assert_output(result)

        # Strip ANSI codes for numeric checks
        plain = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)

        # Denominator must be 200K (context_window_size), not 160K (compaction_threshold)
        assert '/200' in plain, f"Expected /200K denominator but got: {plain!r}"
        assert '/160' not in plain, f"Got /160K denominator leak in: {plain!r}"


# ============================================
# Cache Tests
# ============================================

class TestBlockStatsCache:
    """Tests for _get_cached_block_data() 30s TTL file cache."""

    def _make_cache_data(self, session_id="test-session", age=0):
        """Build valid cache data dict."""
        return {
            'timestamp': time.time() - age,
            'session_id': session_id,
            'block_stats': {
                'start_time': '2026-02-26T05:00:00',
                'duration_seconds': 3600,
                'total_tokens': 100000,
                'input_tokens': 60000,
                'output_tokens': 40000,
                'cache_creation': 5000,
                'cache_read': 20000,
                'total_messages': 50,
            },
            'current_block': {
                'start_time': '2026-02-26T05:00:00',
                'end_time': '2026-02-26T10:00:00',
                'actual_end_time': '2026-02-26T06:00:00',
                'duration_seconds': 3600,
                'is_active': True,
                'messages': [
                    {
                        'timestamp': '2026-02-26T05:30:00+09:00',
                        'session_id': 'test-session',
                        'type': 'assistant',
                        'usage': {'input_tokens': 1000, 'output_tokens': 500},
                        'uuid': 'msg-1',
                        'requestId': 'req-1',
                    }
                ],
            },
        }

    def test_cache_hit_within_ttl(self, tmp_path):
        """Fresh cache returns data without recomputation."""
        cache_file = tmp_path / '.block_stats_cache.json'
        data = self._make_cache_data(age=5)
        import json as _json
        cache_file.write_text(_json.dumps(data))

        with patch.object(statusline, '_get_block_stats_cache_file', return_value=cache_file):
            with patch.object(statusline, 'load_all_messages_chronologically') as mock_load:
                bs, cb = statusline._get_cached_block_data('test-session')
                mock_load.assert_not_called()

        assert bs is not None
        assert bs['total_tokens'] == 100000
        assert isinstance(bs['start_time'], datetime)
        assert cb is not None
        assert len(cb['messages']) == 1
        assert isinstance(cb['messages'][0]['timestamp'], datetime)

    def test_cache_miss_expired_ttl(self, tmp_path):
        """Expired cache triggers recomputation."""
        cache_file = tmp_path / '.block_stats_cache.json'
        data = self._make_cache_data(age=60)  # well past 30s TTL
        import json as _json
        cache_file.write_text(_json.dumps(data))

        with patch.object(statusline, '_get_block_stats_cache_file', return_value=cache_file):
            with patch.object(statusline, 'load_all_messages_chronologically', return_value=[]) as mock_load:
                bs, cb = statusline._get_cached_block_data('test-session')
                mock_load.assert_called_once()

    def test_cache_miss_session_mismatch(self, tmp_path):
        """Cache for a different session_id triggers recomputation."""
        cache_file = tmp_path / '.block_stats_cache.json'
        data = self._make_cache_data(session_id='other-session', age=5)
        import json as _json
        cache_file.write_text(_json.dumps(data))

        with patch.object(statusline, '_get_block_stats_cache_file', return_value=cache_file):
            with patch.object(statusline, 'load_all_messages_chronologically', return_value=[]) as mock_load:
                bs, cb = statusline._get_cached_block_data('test-session')
                mock_load.assert_called_once()

    def test_cache_miss_no_file(self, tmp_path):
        """No cache file triggers recomputation."""
        cache_file = tmp_path / '.block_stats_cache.json'

        with patch.object(statusline, '_get_block_stats_cache_file', return_value=cache_file):
            with patch.object(statusline, 'load_all_messages_chronologically', return_value=[]) as mock_load:
                bs, cb = statusline._get_cached_block_data('test-session')
                mock_load.assert_called_once()

    def test_cache_written_after_computation(self, tmp_path):
        """Cache file is created after a fresh computation."""
        cache_file = tmp_path / '.block_stats_cache.json'

        mock_block = {
            'start_time': datetime(2026, 2, 26, 5, 0, tzinfo=timezone.utc).replace(tzinfo=None),
            'end_time': datetime(2026, 2, 26, 10, 0, tzinfo=timezone.utc).replace(tzinfo=None),
            'actual_end_time': datetime(2026, 2, 26, 6, 0, tzinfo=timezone.utc).replace(tzinfo=None),
            'duration_seconds': 3600,
            'is_active': True,
            'messages': [],
        }
        mock_stats = {
            'start_time': datetime(2026, 2, 26, 5, 0),
            'duration_seconds': 3600,
            'total_tokens': 5000,
            'input_tokens': 3000,
            'output_tokens': 2000,
            'cache_creation': 0,
            'cache_read': 0,
            'total_messages': 10,
        }

        with patch.object(statusline, '_get_block_stats_cache_file', return_value=cache_file):
            with patch.object(statusline, 'load_all_messages_chronologically', return_value=[]):
                with patch.object(statusline, 'detect_five_hour_blocks', return_value=[mock_block]):
                    with patch.object(statusline, 'find_current_session_block', return_value=mock_block):
                        with patch.object(statusline, 'calculate_block_statistics_with_deduplication', return_value=mock_stats):
                            bs, cb = statusline._get_cached_block_data('test-session')

        assert cache_file.exists()
        import json as _json
        cached = _json.loads(cache_file.read_text())
        assert cached['session_id'] == 'test-session'
        assert cached['block_stats']['total_tokens'] == 5000


class TestTranscriptStatsCache:
    """Tests for transcript stats 15s TTL file cache."""

    def _make_transcript(self, tmp_path, content='{"type":"user","timestamp":"2026-02-26T05:00:00Z"}\n'):
        """Create a temporary transcript file."""
        f = tmp_path / 'transcript.jsonl'
        f.write_text(content)
        return f

    def test_cache_hit_within_ttl(self, tmp_path):
        """Fresh cache returns data without re-reading the JSONL file."""
        transcript = self._make_transcript(tmp_path)
        cache_file = tmp_path / '.transcript_stats_cache.json'

        import json as _json
        cache_data = {
            'timestamp': time.time(),
            'file_path': str(transcript),
            'file_mtime': transcript.stat().st_mtime,
            'total_tokens': 9999,
            'message_count': 5,
            'error_count': 0,
            'user_messages': 3,
            'assistant_messages': 2,
            'input_tokens': 5000,
            'output_tokens': 4999,
            'cache_creation': 0,
            'cache_read': 0,
        }
        cache_file.write_text(_json.dumps(cache_data))

        with patch.object(statusline, '_get_transcript_stats_cache_file', return_value=cache_file):
            result = statusline.calculate_tokens_from_transcript(transcript)

        assert result[0] == 9999  # total_tokens from cache

    def test_cache_miss_mtime_changed(self, tmp_path):
        """Cache invalidated when file mtime changes (new messages added)."""
        transcript = self._make_transcript(tmp_path)
        cache_file = tmp_path / '.transcript_stats_cache.json'

        import json as _json
        cache_data = {
            'timestamp': time.time(),
            'file_path': str(transcript),
            'file_mtime': transcript.stat().st_mtime - 1,  # stale mtime
            'total_tokens': 9999,
            'message_count': 5,
            'error_count': 0,
            'user_messages': 3,
            'assistant_messages': 2,
            'input_tokens': 5000,
            'output_tokens': 4999,
            'cache_creation': 0,
            'cache_read': 0,
        }
        cache_file.write_text(_json.dumps(cache_data))

        with patch.object(statusline, '_get_transcript_stats_cache_file', return_value=cache_file):
            result = statusline.calculate_tokens_from_transcript(transcript)

        # Should re-read file; the simple transcript has no assistant usage -> 0 tokens
        assert result[0] == 0

    def test_cache_miss_expired_ttl(self, tmp_path):
        """Expired cache triggers re-read."""
        transcript = self._make_transcript(tmp_path)
        cache_file = tmp_path / '.transcript_stats_cache.json'

        import json as _json
        cache_data = {
            'timestamp': time.time() - 30,  # expired
            'file_path': str(transcript),
            'file_mtime': transcript.stat().st_mtime,
            'total_tokens': 9999,
            'message_count': 5,
            'error_count': 0,
            'user_messages': 3,
            'assistant_messages': 2,
            'input_tokens': 5000,
            'output_tokens': 4999,
            'cache_creation': 0,
            'cache_read': 0,
        }
        cache_file.write_text(_json.dumps(cache_data))

        with patch.object(statusline, '_get_transcript_stats_cache_file', return_value=cache_file):
            result = statusline.calculate_tokens_from_transcript(transcript)

        assert result[0] == 0  # re-read: no real tokens in the simple transcript

    def test_cache_written_after_computation(self, tmp_path):
        """Cache file is created after a fresh computation."""
        transcript = self._make_transcript(tmp_path)
        cache_file = tmp_path / '.transcript_stats_cache.json'

        with patch.object(statusline, '_get_transcript_stats_cache_file', return_value=cache_file):
            statusline.calculate_tokens_from_transcript(transcript)

        assert cache_file.exists()
        import json as _json
        cached = _json.loads(cache_file.read_text())
        assert cached['file_path'] == str(transcript)
        assert cached['file_mtime'] == transcript.stat().st_mtime


# ============================================
# Test Group 1: get_total_tokens() — Token aggregation
# ============================================


class TestGetTotalTokens:
    def test_none_returns_zero(self):
        assert statusline.get_total_tokens(None) == 0

    def test_empty_dict_returns_zero(self):
        assert statusline.get_total_tokens({}) == 0

    def test_input_output_only(self):
        usage = {'input_tokens': 1000, 'output_tokens': 500}
        assert statusline.get_total_tokens(usage) == 1500

    def test_cache_snake_case(self):
        usage = {
            'input_tokens': 100,
            'output_tokens': 50,
            'cache_creation_input_tokens': 200,
            'cache_read_input_tokens': 300,
        }
        assert statusline.get_total_tokens(usage) == 650

    def test_camel_case(self):
        usage = {
            'input_tokens': 100,
            'output_tokens': 50,
            'cacheCreationInputTokens': 200,
            'cacheReadInputTokens': 300,
        }
        assert statusline.get_total_tokens(usage) == 650

    def test_all_fields_mixed(self):
        """snake_case fields take priority over camelCase."""
        usage = {
            'input_tokens': 1000,
            'output_tokens': 2000,
            'cache_creation_input_tokens': 500,
            'cache_read_input_tokens': 300,
            'cacheCreationInputTokens': 9999,  # should be ignored
        }
        assert statusline.get_total_tokens(usage) == 3800


# ============================================
# Test Group 2: get_git_info() — Git integration
# ============================================


class TestGetGitInfo:
    def test_normal_branch_and_status(self, tmp_path):
        git_dir = tmp_path / '.git'
        git_dir.mkdir()
        (git_dir / 'HEAD').write_text('ref: refs/heads/main\n')

        porcelain = " M file1.py\n M file2.py\n?? new_file.txt\n"
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=porcelain, returncode=0)
            branch, modified, untracked = statusline.get_git_info(str(tmp_path))

        assert branch == 'main'
        assert modified == 2
        assert untracked == 1

    def test_no_git_dir(self, tmp_path):
        branch, modified, untracked = statusline.get_git_info(str(tmp_path))
        assert branch is None
        assert modified == 0
        assert untracked == 0

    def test_git_status_timeout(self, tmp_path):
        git_dir = tmp_path / '.git'
        git_dir.mkdir()
        (git_dir / 'HEAD').write_text('ref: refs/heads/feature-x\n')

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('git', 1)):
            branch, modified, untracked = statusline.get_git_info(str(tmp_path))

        assert branch == 'feature-x'
        assert modified == 0
        assert untracked == 0

    def test_detached_head(self, tmp_path):
        git_dir = tmp_path / '.git'
        git_dir.mkdir()
        (git_dir / 'HEAD').write_text('abc123def456\n')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='', returncode=0)
            branch, modified, untracked = statusline.get_git_info(str(tmp_path))

        assert branch is None  # not a ref: line
        assert modified == 0
        assert untracked == 0


# ============================================
# Test Group 3: convert_utc_to_local() / convert_local_to_utc()
# ============================================


class TestTimezoneConversions:
    def test_aware_utc_to_local(self):
        utc_time = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        local = statusline.convert_utc_to_local(utc_time)
        assert local.tzinfo is not None
        # Round-trip: converting back to UTC should match original
        back_to_utc = local.astimezone(timezone.utc)
        assert back_to_utc == utc_time

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime(2026, 1, 15, 12, 0, 0)
        local = statusline.convert_utc_to_local(naive)
        assert local.tzinfo is not None

    def test_roundtrip(self):
        utc_time = datetime(2026, 6, 15, 18, 30, 0, tzinfo=timezone.utc)
        local = statusline.convert_utc_to_local(utc_time)
        back = statusline.convert_local_to_utc(local)
        assert abs((back - utc_time).total_seconds()) < 1

    def test_convert_local_to_utc_naive(self):
        naive = datetime(2026, 1, 15, 12, 0, 0)
        result = statusline.convert_local_to_utc(naive)
        # Naive is treated as UTC by replace(tzinfo=utc)
        assert result.tzinfo == timezone.utc
        assert result.hour == 12


# ============================================
# Test Group 4: detect_five_hour_blocks()
# ============================================


class TestDetectFiveHourBlocks:
    def _make_msg(self, ts, session_id='s1'):
        """Build a minimal message dict with a naive UTC timestamp."""
        return {
            'timestamp': ts,
            'session_id': session_id,
            'type': 'assistant',
            'usage': {'input_tokens': 100, 'output_tokens': 50},
        }

    def test_empty_list(self):
        assert statusline.detect_five_hour_blocks([]) == []

    def test_single_cluster_within_one_hour(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        msgs = [
            self._make_msg(now - timedelta(minutes=30)),
            self._make_msg(now - timedelta(minutes=20)),
            self._make_msg(now - timedelta(minutes=10)),
        ]
        blocks = statusline.detect_five_hour_blocks(msgs)
        assert len(blocks) == 1
        assert len(blocks[0]['messages']) == 3

    def test_two_groups_with_gap(self):
        """6-hour gap between groups should produce 2 blocks."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        group1 = [
            self._make_msg(now - timedelta(hours=5, minutes=50)),
            self._make_msg(now - timedelta(hours=5, minutes=40)),
        ]
        group2 = [
            self._make_msg(now - timedelta(minutes=20)),
            self._make_msg(now - timedelta(minutes=10)),
        ]
        blocks = statusline.detect_five_hour_blocks(group1 + group2)
        assert len(blocks) == 2

    def test_boundary_within_five_hours(self):
        """Messages within 5h of floored block start should stay in one block."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Start within last 4h so all fit in 6h recency + 5h block window
        start = now - timedelta(hours=3)
        msgs = [
            self._make_msg(start),
            self._make_msg(start + timedelta(hours=1)),
            self._make_msg(start + timedelta(hours=2, minutes=50)),
        ]
        blocks = statusline.detect_five_hour_blocks(msgs)
        assert len(blocks) == 1

    def test_is_active_flag(self):
        """Recent messages should mark the block as active."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        msgs = [self._make_msg(now - timedelta(seconds=30))]
        with patch('statusline.datetime') as mock_dt:
            # Make sure now() returns our 'now'
            mock_dt.now.return_value = now.replace(tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            blocks = statusline.detect_five_hour_blocks(msgs)
        assert len(blocks) == 1
        assert blocks[0]['is_active'] is True


# ============================================
# Test Group 5: generate_real_burn_timeline()
# ============================================


class TestGenerateRealBurnTimeline:
    def test_no_messages(self):
        result = statusline.generate_real_burn_timeline({}, None)
        assert result == [0] * 20

    def test_single_message(self):
        start = datetime(2026, 3, 1, 10, 0, 0)  # naive UTC
        block_stats = {'start_time': start}
        msg = {
            'type': 'assistant',
            'usage': {'input_tokens': 500, 'output_tokens': 200},
            'timestamp': start + timedelta(minutes=7),  # segment 0
        }
        current_block = {'messages': [msg]}
        result = statusline.generate_real_burn_timeline(block_stats, current_block)
        assert result[0] == 700  # 500 + 200
        assert sum(result[1:]) == 0  # all other segments zero

    def test_multiple_segments(self):
        start = datetime(2026, 3, 1, 10, 0, 0)
        block_stats = {'start_time': start}
        msgs = [
            {
                'type': 'assistant',
                'usage': {'input_tokens': 100, 'output_tokens': 50},
                'timestamp': start + timedelta(minutes=5),  # segment 0
            },
            {
                'type': 'assistant',
                'usage': {'input_tokens': 200, 'output_tokens': 100},
                'timestamp': start + timedelta(minutes=20),  # segment 1
            },
            {
                'type': 'assistant',
                'usage': {'input_tokens': 300, 'output_tokens': 150},
                'timestamp': start + timedelta(minutes=60),  # segment 4
            },
        ]
        current_block = {'messages': msgs}
        result = statusline.generate_real_burn_timeline(block_stats, current_block)
        assert result[0] == 150   # 100+50
        assert result[1] == 300   # 200+100
        assert result[4] == 450   # 300+150

    def test_total_matches_message_sum(self):
        start = datetime(2026, 3, 1, 10, 0, 0)
        block_stats = {'start_time': start}
        msgs = []
        expected_total = 0
        for i in range(5):
            tokens = (i + 1) * 100
            msgs.append({
                'type': 'assistant',
                'usage': {'input_tokens': tokens, 'output_tokens': 0},
                'timestamp': start + timedelta(minutes=i * 20),
            })
            expected_total += tokens
        current_block = {'messages': msgs}
        result = statusline.generate_real_burn_timeline(block_stats, current_block)
        assert sum(result) == expected_total


# ============================================
# Test Group 6: build_line1_parts()
# ============================================


class TestBuildLine1Parts:
    @staticmethod
    def _make_ctx(**overrides):
        base = {
            'model': 'Claude Opus 4.6',
            'git_branch': 'main',
            'modified_files': 2,
            'untracked_files': 1,
            'current_dir': 'statusline',
            'active_files': 3,
            'total_messages': 50,
            'lines_added': 10,
            'lines_removed': 5,
            'error_count': 2,
            'session_cost': 1.23,
            'context_size': 200000,
        }
        base.update(overrides)
        return base

    def test_all_flags_true(self):
        ctx = self._make_ctx()
        parts = statusline.build_line1_parts(ctx)
        joined = statusline.strip_ansi(" ".join(parts))
        assert 'Opus 4.6' in joined
        assert 'main' in joined
        assert 'statusline' in joined
        assert '50' in joined  # messages
        assert '$1.23' in joined  # cost

    def test_all_flags_false(self):
        ctx = self._make_ctx()
        parts = statusline.build_line1_parts(
            ctx,
            include_active_files=False,
            include_messages=False,
            include_lines=False,
            include_errors=False,
            include_cost=False,
            include_dir=False,
        )
        joined = statusline.strip_ansi(" ".join(parts))
        # Model and branch should remain
        assert 'Opus 4.6' in joined
        assert 'main' in joined
        # These should be absent
        assert '$1.23' not in joined
        assert 'statusline' not in joined

    def test_tight_model(self):
        ctx = self._make_ctx()
        parts = statusline.build_line1_parts(ctx, tight_model=True)
        joined = statusline.strip_ansi(" ".join(parts))
        assert 'Op4.6' in joined

    def test_truncation(self):
        ctx = self._make_ctx(git_branch='very-long-branch-name-exceeds-limit')
        parts = statusline.build_line1_parts(ctx, max_branch_len=10, max_dir_len=5)
        joined = statusline.strip_ansi(" ".join(parts))
        assert '...' in joined  # truncation applied


# ============================================
# Test Group 7: Formatter smoke tests
# ============================================


class TestFormatters:
    @staticmethod
    def _make_full_ctx():
        return {
            'model': 'Claude Sonnet 4.6',
            'git_branch': 'main',
            'modified_files': 1,
            'untracked_files': 0,
            'current_dir': 'project',
            'active_files': 2,
            'total_messages': 100,
            'lines_added': 20,
            'lines_removed': 5,
            'error_count': 0,
            'task_status': None,
            'session_cost': 2.50,
            'compact_tokens': 80000,
            'compaction_threshold': 160000,
            'percentage': 50,
            'cache_ratio': 85,
            'session_duration': '1h30m',
            'block_progress': 30,
            'session_time_info': None,
            'burn_line': None,
            'burn_timeline': [1000, 2000, 500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'block_tokens': 50000,
            'weekly_line': 'Weekly: [40%]',
            'weekly_timeline': None,
            'ratelimit_data': None,
            'api_session_range': ('10am', '3pm'),
            'five_hour_utilization': 30,
            'session_duration_seconds': 5400,
            'show_line1': True,
            'show_line2': True,
            'show_line3': True,
            'show_line4': True,
            'show_schedule': False,
            'exceeds_200k': False,
            'context_size': 200000,
            'percentage_of_full_context': 50,
        }

    def test_format_output_full(self):
        ctx = self._make_full_ctx()
        lines = statusline.format_output_full(ctx, terminal_width=80)
        assert isinstance(lines, list)
        assert len(lines) == 4
        for line in lines:
            assert len(statusline.strip_ansi(line)) > 0

    def test_format_output_compact(self):
        ctx = self._make_full_ctx()
        lines = statusline.format_output_compact(ctx)
        assert isinstance(lines, list)
        assert len(lines) == 4
        for line in lines:
            assert len(statusline.strip_ansi(line)) > 0

    def test_format_output_tight(self):
        ctx = self._make_full_ctx()
        lines = statusline.format_output_tight(ctx)
        assert isinstance(lines, list)
        assert len(lines) == 4
        for line in lines:
            assert len(statusline.strip_ansi(line)) > 0

    def test_format_output_minimal(self):
        ctx = self._make_full_ctx()
        lines = statusline.format_output_minimal(ctx, terminal_width=40)
        assert isinstance(lines, list)
        assert len(lines) == 1
        assert len(statusline.strip_ansi(lines[0])) > 0


# ============================================
# Test Group 8: calculate_tokens_from_jsonl_with_dedup()
# ============================================


class TestCalculateTokensFromJsonlWithDedup:
    def _write_jsonl(self, path, messages):
        with open(path, 'w') as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')

    def test_normal_assistant_messages(self, tmp_path):
        transcript = tmp_path / 'session.jsonl'
        start = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        msgs = [
            {
                'type': 'assistant',
                'timestamp': (start + timedelta(minutes=5)).isoformat(),
                'uuid': 'msg-1',
                'requestId': 'req-1',
                'usage': {
                    'input_tokens': 1000,
                    'output_tokens': 500,
                    'cache_creation_input_tokens': 0,
                    'cache_read_input_tokens': 0,
                },
            },
            {
                'type': 'assistant',
                'timestamp': (start + timedelta(minutes=10)).isoformat(),
                'uuid': 'msg-2',
                'requestId': 'req-2',
                'usage': {
                    'input_tokens': 2000,
                    'output_tokens': 1000,
                    'cache_creation_input_tokens': 0,
                    'cache_read_input_tokens': 0,
                },
            },
        ]
        self._write_jsonl(transcript, msgs)
        result = statusline.calculate_tokens_from_jsonl_with_dedup(
            transcript, start, 18000  # 5h
        )
        assert result is not None
        assert result['total_tokens'] == 4500  # 1000+500+2000+1000
        assert result['assistant_messages'] == 2

    def test_duplicate_uuid_requestid(self, tmp_path):
        transcript = tmp_path / 'session.jsonl'
        start = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        msg = {
            'type': 'assistant',
            'timestamp': (start + timedelta(minutes=5)).isoformat(),
            'uuid': 'msg-dup',
            'requestId': 'req-dup',
            'usage': {
                'input_tokens': 1000,
                'output_tokens': 500,
                'cache_creation_input_tokens': 0,
                'cache_read_input_tokens': 0,
            },
        }
        self._write_jsonl(transcript, [msg, msg, msg])  # 3 copies
        result = statusline.calculate_tokens_from_jsonl_with_dedup(
            transcript, start, 18000
        )
        assert result is not None
        assert result['total_tokens'] == 1500  # only 1 counted
        assert result['skipped_duplicates'] == 2

    def test_outside_time_window(self, tmp_path):
        transcript = tmp_path / 'session.jsonl'
        start = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        msg = {
            'type': 'assistant',
            'timestamp': (start - timedelta(hours=2)).isoformat(),  # before window
            'uuid': 'msg-old',
            'requestId': 'req-old',
            'usage': {
                'input_tokens': 9999,
                'output_tokens': 9999,
                'cache_creation_input_tokens': 0,
                'cache_read_input_tokens': 0,
            },
        }
        self._write_jsonl(transcript, [msg])
        result = statusline.calculate_tokens_from_jsonl_with_dedup(
            transcript, start, 18000
        )
        assert result is not None
        assert result['total_tokens'] == 0

    def test_empty_file(self, tmp_path):
        transcript = tmp_path / 'session.jsonl'
        transcript.write_text('')
        result = statusline.calculate_tokens_from_jsonl_with_dedup(
            transcript, datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc), 18000
        )
        assert result is not None
        assert result['total_tokens'] == 0
        assert result['total_messages'] == 0


# ============================================
# Test Group 9: find_session_transcript()
# ============================================


class TestFindSessionTranscript:
    def test_none_session_id(self):
        assert statusline.find_session_transcript(None) is None

    def test_existing_session(self, tmp_path):
        projects_dir = tmp_path / '.claude' / 'projects' / 'test-project'
        projects_dir.mkdir(parents=True)
        transcript = projects_dir / 'abc-123.jsonl'
        transcript.write_text('{"type":"user"}\n')

        with patch.object(Path, 'home', return_value=tmp_path):
            result = statusline.find_session_transcript('abc-123')
        assert result is not None
        assert result.name == 'abc-123.jsonl'

    def test_nonexistent_session(self, tmp_path):
        projects_dir = tmp_path / '.claude' / 'projects' / 'test-project'
        projects_dir.mkdir(parents=True)

        with patch.object(Path, 'home', return_value=tmp_path):
            result = statusline.find_session_transcript('nonexistent-id')
        assert result is None


# ============================================
# Test Group 10: format_schedule_line()
# ============================================


class TestFormatScheduleLine:
    def test_normal_event(self):
        event = {
            'time': '14:00',
            'summary': 'Meeting',
            'minutes_until': 30,
            'is_all_day': False,
        }
        result = statusline.format_schedule_line(event, 60)
        assert result is not None
        clean = statusline.strip_ansi(result)
        assert '14:00' in clean
        assert 'Meeting' in clean
        assert '30m' in clean

    def test_narrow_width_truncates(self):
        event = {
            'time': '14:00',
            'summary': 'Very Long Meeting Summary That Exceeds Width',
            'minutes_until': 30,
            'is_all_day': False,
        }
        result = statusline.format_schedule_line(event, 30)
        assert result is not None
        clean = statusline.strip_ansi(result)
        # Should be truncated to fit
        assert len(clean) <= 35  # some margin for emoji width

    def test_cjk_summary(self):
        event = {
            'time': '14:00',
            'summary': '\u30df\u30fc\u30c6\u30a3\u30f3\u30b0\u306e\u4e88\u5b9a\u304c\u3042\u308a\u307e\u3059',
            'minutes_until': 60,
            'is_all_day': False,
        }
        result = statusline.format_schedule_line(event, 40)
        assert result is not None
        # Just verify it doesn't crash with CJK


# ============================================
# Test Group 11: format_agent_line() / get_dead_agents()
# ============================================


class TestAgentFunctions:
    def test_format_agent_line(self):
        ctx = {
            'model': 'Claude Sonnet 4.6',
            'total_messages': 25,
            'percentage': 40,
            'session_cost': 0.50,
        }
        result = statusline.format_agent_line(ctx, 'researcher')
        clean = statusline.strip_ansi(result)
        assert 'researcher' in clean
        assert 'Sonnet 4.6' in clean

    def test_get_dead_agents_no_file(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            assert statusline.get_dead_agents() == []

    def test_get_dead_agents_with_file(self, tmp_path):
        dead_file = tmp_path / 'tproj-dead-agents'
        dead_file.write_text('agent-1\nagent-2\n')
        with patch('builtins.open', return_value=open(dead_file, 'r')):
            agents = statusline.get_dead_agents()
        assert agents == ['agent-1', 'agent-2']


# ============================================
# Test Group 12: E2E smoke additions
# ============================================


class TestSmokeExtended:
    """Extended smoke tests with realistic input data."""

    def _run(self, input_data):
        return subprocess.run(
            [sys.executable, STATUSLINE_PATH],
            input=input_data,
            capture_output=True, text=True,
            timeout=10,
        )

    def test_full_input_with_ratelimit(self):
        data = json.dumps({
            "session_id": "test-full",
            "transcript_path": "/tmp/nonexistent.jsonl",
            "cwd": "/tmp/project",
            "model": {"id": "claude-opus-4-6", "display_name": "Opus 4.6"},
            "workspace": {"current_dir": "/tmp/project", "project_dir": "/tmp", "added_dirs": []},
            "version": "2.2.0",
            "output_style": {"name": "default"},
            "cost": {
                "total_cost_usd": 1.5,
                "total_duration_ms": 360000,
                "total_api_duration_ms": 120000,
                "total_lines_added": 50,
                "total_lines_removed": 10,
            },
            "context_window": {
                "total_input_tokens": 50000,
                "total_output_tokens": 20000,
                "context_window_size": 200000,
                "current_usage": {
                    "input_tokens": 60000,
                    "output_tokens": 20000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "used_percentage": 40,
                "remaining_percentage": 60,
            },
            "ratelimit": {
                "five_hour": {
                    "utilization": 25,
                    "resets_at": "2026-03-02T15:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 40,
                    "resets_at": "2026-03-08T00:00:00+00:00",
                },
            },
            "exceeds_200k_tokens": False,
        })
        result = self._run(data)
        assert result.returncode == 0
        lines = result.stdout.strip().split('\n')
        assert len(lines) >= 4, f"Expected >= 4 lines, got {len(lines)}: {result.stdout!r}"

    def test_show_simple(self):
        data = json.dumps({
            "model": {"display_name": "Sonnet 4.6"},
            "context_window": {
                "context_window_size": 200000,
                "used_percentage": 30,
            },
        })
        result = subprocess.run(
            [sys.executable, STATUSLINE_PATH, '--show', 'simple'],
            input=data,
            capture_output=True, text=True,
            timeout=10,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split('\n')
        assert len(lines) <= 2, f"Simple mode should be <= 2 lines, got {len(lines)}"

    def test_show_specific_lines(self):
        data = json.dumps({
            "model": {"display_name": "Opus 4.6"},
            "context_window": {
                "context_window_size": 200000,
                "used_percentage": 50,
            },
        })
        result = subprocess.run(
            [sys.executable, STATUSLINE_PATH, '--show', '1,2'],
            input=data,
            capture_output=True, text=True,
            timeout=10,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split('\n')
        assert len(lines) <= 2, f"--show 1,2 should be <= 2 lines, got {len(lines)}"
