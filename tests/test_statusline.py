"""Tests for statusline.py — unit tests + smoke tests."""

import json
import os
import re
import subprocess
import sys

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

    def test_compact(self):
        assert statusline.get_display_mode(35) == "compact"
        assert statusline.get_display_mode(67) == "compact"

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
