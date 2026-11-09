"""Offline update regressions. Never contact GitHub or touch a real install."""

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import statusline


def _source(label):
    return ('#!/usr/bin/env python3\n' + '# padding\n' * 110 +
            f'VERSION = {label!r}\ndef main():\n    pass\n').encode()


class Response(io.BytesIO):
    headers = {'ETag': 'new-etag'}


@pytest.fixture
def installed(tmp_path, monkeypatch):
    directory = tmp_path / '.claude'
    directory.mkdir()
    target = directory / 'statusline.py'
    target.write_bytes(_source('installed'))
    monkeypatch.setattr(statusline.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(statusline, '__file__', str(target))
    monkeypatch.setattr(statusline, 'AUTO_UPDATE_CACHE_FILE', None)
    monkeypatch.setattr(statusline, 'AUTO_UPDATE_LOCK_FILE', None)
    monkeypatch.setenv('STATUSLINE_AUTO_UPDATE', '1')
    return target


def test_process_lock_excludes_contenders_and_survives_old_mtime(installed):
    lock = statusline._acquire_update_lock()
    assert lock is not None
    lock_path = statusline.get_update_lock_file()
    os.utime(lock_path, (1, 1))  # a live update cannot be stolen after a time limit
    script = (
        'import statusline\nfrom pathlib import Path\n'
        f'statusline.AUTO_UPDATE_LOCK_FILE = Path({str(lock_path)!r})\n'
        'handle = statusline._acquire_update_lock()\n'
        'print("busy" if handle is None else "acquired")\n'
        # Deliberately exit without releasing: the OS must recover the lock.
    )
    def contender():
        return subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    try:
        assert contender() == 'busy'
    finally:
        statusline._release_update_lock(lock)
    assert contender() == 'acquired'
    recovered = statusline._acquire_update_lock()
    assert recovered is not None
    statusline._release_update_lock(recovered)
    assert lock_path.exists()  # stable inode; no unlock-by-unlink race


def test_update_and_rollback_share_lock(installed):
    installed.with_name('statusline.py.backup').write_bytes(_source('backup'))
    lock = statusline._acquire_update_lock()
    assert lock is not None
    try:
        with patch('urllib.request.urlopen') as request:
            assert statusline.do_self_update() is False
            assert statusline.do_update_foreground() is False
            assert statusline.do_rollback() is False
        request.assert_not_called()
        assert installed.read_bytes() == _source('installed')
    finally:
        statusline._release_update_lock(lock)


def test_background_installs_once_and_keeps_the_previous_version(installed):
    with patch('urllib.request.urlopen', return_value=Response(_source('new'))) as request:
        assert statusline.do_self_update()
        assert statusline.do_self_update()  # another already-launched child sees fresh metadata
    assert request.call_count == 1
    assert installed.read_bytes() == _source('new')
    assert installed.with_name('statusline.py.backup').read_bytes() == _source('installed')
    assert not list(installed.parent.glob('*.tmp'))


@pytest.mark.parametrize('disabled', ['environment', 'marker', 'symlink'])
def test_direct_background_entry_honors_update_guards(installed, monkeypatch, disabled):
    if disabled == 'environment':
        monkeypatch.setenv('STATUSLINE_AUTO_UPDATE', '0')
    elif disabled == 'marker':
        (installed.parent / '.statusline_no_update').touch()
    else:
        development = installed.with_name('development.py')
        installed.rename(development)
        installed.symlink_to(development)
    with patch('urllib.request.urlopen') as request:
        assert statusline.do_self_update() is False
    request.assert_not_called()
    assert installed.read_bytes() == _source('installed')


def test_policy_change_during_download_aborts_install(installed):
    def download(request, timeout):
        (installed.parent / '.statusline_no_update').touch()
        return Response(_source('new'))
    with patch('urllib.request.urlopen', side_effect=download):
        assert statusline.do_self_update() is False
    assert installed.read_bytes() == _source('installed')
    assert not installed.with_name('statusline.py.backup').exists()


@pytest.mark.parametrize('cached_hash_matches', [True, False])
def test_conditional_requests_only_describe_the_installed_content(installed, cached_hash_matches):
    digest = hashlib.sha256(installed.read_bytes()).hexdigest() if cached_hash_matches else 'other-content'
    statusline._save_update_cache({'etag': 'previous-etag', 'content_hash': digest, 'last_check': 0})
    seen = []
    def download(request, timeout):
        seen.append(request.get_header('If-none-match'))
        if cached_hash_matches:
            raise HTTPError(statusline.AUTO_UPDATE_URL, 304, 'Not Modified', {}, None)
        return Response(_source('new'))
    with patch('urllib.request.urlopen', side_effect=download):
        assert statusline.do_update_foreground()
    assert seen == ['previous-etag' if cached_hash_matches else None]
    assert installed.read_bytes() == _source('installed' if cached_hash_matches else 'new')


def test_rollback_clears_etag_and_next_explicit_update_fetches(installed):
    installed.with_name('statusline.py.backup').write_bytes(_source('older'))
    statusline._save_update_cache({'etag': 'installed-etag',
                                  'content_hash': hashlib.sha256(installed.read_bytes()).hexdigest()})
    assert statusline.do_rollback()
    assert installed.read_bytes() == _source('older')
    assert 'etag' not in statusline.load_update_cache()
    with patch('urllib.request.urlopen', return_value=Response(_source('installed'))) as request:
        assert statusline.do_update_foreground()
    assert not request.call_args.args[0].has_header('If-none-match')
    assert installed.read_bytes() == _source('installed')


@pytest.mark.parametrize('content', [b'<html>error</html>', _source('new') + b'not python @@'])
def test_invalid_download_preserves_install_and_releases_lock(installed, content):
    with patch('urllib.request.urlopen', return_value=Response(content)):
        assert statusline.do_self_update() is False
    assert installed.read_bytes() == _source('installed')
    assert not installed.with_name('statusline.py.backup').exists()
    lock = statusline._acquire_update_lock()
    assert lock is not None
    statusline._release_update_lock(lock)
    assert statusline.load_update_cache()['last_check'] > 0


def test_backup_failure_aborts_without_changing_install(installed):
    with patch('urllib.request.urlopen', return_value=Response(_source('new'))), \
         patch.object(statusline, '_atomic_write_update_file', side_effect=OSError('disk full')):
        assert statusline.do_self_update() is False
    assert installed.read_bytes() == _source('installed')
    assert not list(installed.parent.glob('*.tmp'))


def test_lock_symlink_cannot_modify_another_file(installed):
    victim = installed.with_name('unrelated.json')
    victim.write_text('{"keep":true}')
    statusline.get_update_lock_file().symlink_to(victim)
    with patch('urllib.request.urlopen') as request:
        assert statusline.do_update_foreground() is False
    request.assert_not_called()
    assert json.loads(victim.read_text()) == {'keep': True}


def test_malformed_metadata_does_not_disable_future_checks(installed):
    malformed = [{'last_check': 'not-a-number'}, {'last_check': float('nan')},
                 {'last_check': float('inf')}, {'etag': {}}, {'content_hash': []}]
    for payload in malformed:
        statusline.get_update_cache_file().write_text(json.dumps(payload))
        with patch.object(statusline.subprocess, 'Popen') as spawn:
            statusline.maybe_check_update()
        spawn.assert_called_once()
