"""Keep unit and subprocess tests away from the developer's live sessions."""

import sys

import pytest


@pytest.fixture(autouse=True)
def isolated_installation(tmp_path, monkeypatch):
    home = tmp_path / 'test-home'
    (home / '.claude').mkdir(parents=True)
    # HOME is used on POSIX; USERPROFILE is used by pathlib on Windows.
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('STATUSLINE_AUTO_UPDATE', '0')
    monkeypatch.setenv('STATUSLINE_CCSTATUSBAR_BIN', str(home / 'no-companion'))
    monkeypatch.setenv('COLUMNS', '200')
    monkeypatch.setenv('LINES', '50')
    for key in ('TMUX', 'TMUX_PANE', 'TERM', 'ITERM_SESSION_ID',
                'CCSL_KEEP_WARM_HOURS', 'STATUSLINE_DISPLAY_MODE',
                'STATUSLINE_DEBUG', 'STATUSLINE_DUMP_STDIN', 'STATUSLINE_NO_SCHEMA_WATCH',
                'STATUSLINE_MODE', 'CLAUDE_CODE_AGENT_NAME', 'STATUSLINE_NO_COLOR'):
        monkeypatch.delenv(key, raising=False)

    # These paths are captured at import time, before fixtures run. Override
    # them as well as the environment so in-process tests stay isolated too.
    module = sys.modules.get('statusline')
    if module is not None:
        monkeypatch.setattr(module, 'CCSTATUSBAR_APP_SUPPORT', home / 'companion')
        monkeypatch.setattr(module, 'CCSTATUSBAR_BIN', home / 'no-companion')
        for name in ('AUTO_UPDATE_CACHE_FILE', 'AUTO_UPDATE_LOCK_FILE', 'SCHEDULE_CACHE_FILE'):
            monkeypatch.setattr(module, name, None)
