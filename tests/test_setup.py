"""Installer regressions, isolated from the caller's Claude Code installation."""

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import statusline


def test_setup_preserves_settings_and_update_policy(tmp_path):
    directory = tmp_path / '.claude'
    directory.mkdir()
    settings = directory / 'settings.json'
    settings.write_text(json.dumps({'permissions': {'deny': ['Bash(rm *)']}, 'statusLine': {'custom': True}}))
    state = {'.statusline_no_update': '', 'statusline.py.backup': '# old version',
             '.statusline_update_lock.json': '{"pid":123}', '.statusline_update.json': '{"etag":"old"}'}
    for name, contents in state.items():
        (directory / name).write_text(contents)
    with patch.object(statusline.Path, 'home', return_value=tmp_path):
        assert statusline.do_setup()
    parsed = json.loads(settings.read_text())
    assert parsed['permissions'] == {'deny': ['Bash(rm *)']}
    assert parsed['statusLine']['custom'] is True
    assert all((directory / name).read_text() == contents for name, contents in state.items())


def test_setup_command_runs_with_spaces_and_shell_characters(tmp_path):
    if os.name == 'nt':
        pytest.skip('POSIX shell quoting; Windows uses list2cmdline')
    script = tmp_path / "a folder 'quoted';$name" / 'statusline.py'
    script.parent.mkdir()
    shutil.copyfile(statusline.__file__, script)
    with patch.object(statusline.Path, 'home', return_value=tmp_path):
        assert statusline.do_setup(script_path=script)
    command = json.loads((tmp_path / '.claude' / 'settings.json').read_text())['statusLine']['command']
    assert shlex.split(command) == [sys.executable, str(script)]
    result = subprocess.run(command + ' --version', shell=True, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f'ccsl {statusline.__version__}'


@pytest.mark.parametrize('contents', ['{invalid', '[]'])
def test_setup_leaves_unreadable_schema_intact(tmp_path, contents):
    directory = tmp_path / '.claude'
    directory.mkdir()
    settings = directory / 'settings.json'
    settings.write_text(contents)
    with patch.object(statusline.Path, 'home', return_value=tmp_path):
        assert statusline.do_setup() is False
    assert settings.read_text() == contents


def test_setup_write_failure_preserves_existing_settings(tmp_path):
    directory = tmp_path / '.claude'
    directory.mkdir()
    settings = directory / 'settings.json'
    contents = '{"permissions":{"deny":["Bash(rm *)"]}}'
    settings.write_text(contents)
    with patch.object(statusline.Path, 'home', return_value=tmp_path), \
         patch.object(statusline.os, 'replace', side_effect=OSError('disk full')):
        with pytest.raises(OSError, match='disk full'):
            statusline.do_setup()
    assert settings.read_text() == contents
    assert not list(directory.glob('*.json.tmp'))


def test_source_installer_works_from_other_directory_and_preserves_opt_out(tmp_path, monkeypatch):
    directory = tmp_path / '.claude'
    directory.mkdir()
    (directory / '.statusline_no_update').touch()
    spec = importlib.util.spec_from_file_location('ccsl_installer', Path(statusline.__file__).with_name('install.py'))
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(statusline.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr('builtins.input', lambda prompt: '')
    installer.main()
    script = directory / 'statusline.py'
    assert script.read_bytes() == Path(statusline.__file__).read_bytes()
    command = json.loads((directory / 'settings.json').read_text())['statusLine']['command']
    argv = [sys.executable, str(script)]
    expected = subprocess.list2cmdline(argv) if os.name == 'nt' else shlex.join(argv)
    assert command == expected
    assert (directory / '.statusline_no_update').exists()


def test_source_installer_does_not_overwrite_development_symlink(tmp_path, monkeypatch):
    directory = tmp_path / '.claude'
    directory.mkdir()
    development_file = tmp_path / 'development.py'
    development_file.write_text('# local development work')
    (directory / 'statusline.py').symlink_to(development_file)
    spec = importlib.util.spec_from_file_location('ccsl_installer', Path(statusline.__file__).with_name('install.py'))
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    monkeypatch.setattr(statusline.Path, 'home', lambda: tmp_path)
    with pytest.raises(SystemExit, match='development symlink'):
        installer.main()
    assert development_file.read_text() == '# local development work'
    assert (directory / 'statusline.py').is_symlink()


@pytest.mark.parametrize(('existing', 'expected'), [(None, 5), (5000, 5), (12, 12)])
def test_setup_uses_seconds_and_preserves_custom_refresh_interval(tmp_path, existing, expected):
    directory = tmp_path / '.claude'
    directory.mkdir()
    status_line = {'command': 'ccsl'}
    if existing is not None:
        status_line['refreshInterval'] = existing
    settings = directory / 'settings.json'
    settings.write_text(json.dumps({'statusLine': status_line}))
    with patch.object(statusline.Path, 'home', return_value=tmp_path):
        assert statusline.do_setup()
    assert json.loads(settings.read_text())['statusLine']['refreshInterval'] == expected
