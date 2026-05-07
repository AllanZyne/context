import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _has(bin_name: str) -> bool:
    return shutil.which(bin_name) is not None


@pytest.mark.skipif(not _has("bash"), reason="bash not available")
def test_bash_wrapper_applies_env_writeback(tmp_path: Path):
    """
    Source the bash wrapper, run `ctx set-foo`, verify the parent bash
    process sees FOO in its environment afterwards.
    """
    (tmp_path / "context.yaml").write_text(
        "commands:\n"
        "  set-foo:\n"
        "    run:\n"
        "      - export FOO=bar-from-ctx\n"
    )
    script = f"""
        set -e
        eval "$(uv --directory {REPO_ROOT} run ctx-bin shellinit bash)"
        cd {tmp_path}
        ctx set-foo
        echo "AFTER_FOO=$FOO"
    """
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ},
    )
    assert result.returncode == 0, result.stderr
    assert "AFTER_FOO=bar-from-ctx" in result.stdout


@pytest.mark.skipif(not _has("bash"), reason="bash not available")
def test_bash_wrapper_no_writeback_on_failure(tmp_path: Path):
    (tmp_path / "context.yaml").write_text(
        "commands:\n"
        "  bad:\n"
        "    run:\n"
        "      - export SHOULD_NOT_LEAK=1\n"
        "      - false\n"
    )
    script = f"""
        eval "$(uv --directory {REPO_ROOT} run ctx-bin shellinit bash)"
        cd {tmp_path}
        ctx bad || true
        echo "LEAK=${{SHOULD_NOT_LEAK:-unset}}"
    """
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ},
    )
    assert result.returncode == 0
    assert "LEAK=unset" in result.stdout


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_fish_wrapper_applies_env_writeback(tmp_path: Path):
    (tmp_path / "context.yaml").write_text(
        "commands:\n"
        "  set-foo:\n"
        "    run:\n"
        "      - export FOO=bar-from-ctx\n"
    )
    script = f"""
        uv --directory {REPO_ROOT} run ctx-bin shellinit fish | source
        cd {tmp_path}
        ctx set-foo
        echo "AFTER_FOO=$FOO"
    """
    result = subprocess.run(
        ["fish", "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ},
    )
    assert result.returncode == 0, result.stderr
    assert "AFTER_FOO=bar-from-ctx" in result.stdout
