"""Regression tests for MySQL init script shell isolation."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

INIT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "docker"
    / "mysql"
    / "init"
    / "01-create-test-database.sh"
)


def _bash_executable() -> str:
    bash = shutil.which("bash")
    if sys.platform == "win32" or bash is None:
        pytest.skip("POSIX bash is required to test Docker init script sourcing")
    return bash


def _write_mysql_stub(bin_dir: Path, *, exit_code: int = 0) -> Path:
    stub = bin_dir / "mysql"
    stub.write_text(
        f"#!/usr/bin/env bash\nexit {exit_code}\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _base_env(bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("MYSQL_ONETIME_PASSWORD", None)
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "MYSQL_DATABASE": "retailops",
            "MYSQL_TEST_DATABASE": "retailops_test",
            "MYSQL_USER": "retailops_app",
            "MYSQL_TEST_USER": "retailops_test_runner",
            "MYSQL_ROOT_PASSWORD": "root-password",
            "MYSQL_TEST_PASSWORD": "test-password",
        }
    )
    return env


def test_mysql_init_script_preserves_caller_nounset_when_sourced(
    tmp_path: Path,
) -> None:
    bash = _bash_executable()
    _write_mysql_stub(tmp_path, exit_code=0)
    command = (
        f'set +u; source "{INIT_SCRIPT}"; '
        '[[ "$-" != *u* ]]; '
        'test -z "$MYSQL_ONETIME_PASSWORD"'
    )
    result = subprocess.run(
        [bash, "-c", command],
        env=_base_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("override_key", "override_value", "mysql_exit"),
    [
        ("MYSQL_TEST_DATABASE", "bad-db-name", 0),
        ("MYSQL_TEST_USER", "root", 0),
        ("MYSQL_TEST_DATABASE", "retailops_test", 1),
    ],
)
def test_mysql_init_script_propagates_validation_and_sql_failures(
    tmp_path: Path,
    override_key: str,
    override_value: str,
    mysql_exit: int,
) -> None:
    bash = _bash_executable()
    _write_mysql_stub(tmp_path, exit_code=mysql_exit)
    env = _base_env(tmp_path)
    env[override_key] = override_value
    command = f'set -Eeo pipefail; source "{INIT_SCRIPT}"; echo "SHOULD_NOT_REACH"'
    result = subprocess.run(
        [bash, "-c", command],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "SHOULD_NOT_REACH" not in result.stdout
