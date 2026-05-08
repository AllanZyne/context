import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ctx.shellinit import shellinit


REPO_ROOT = Path(__file__).resolve().parents[1]
BASH_WRAPPER = REPO_ROOT / "shells" / "ctx.bash"
ZSH_WRAPPER = REPO_ROOT / "shells" / "ctx.zsh"
FISH_WRAPPER = REPO_ROOT / "shells" / "ctx.fish"


def _has(bin_name: str) -> bool:
    return shutil.which(bin_name) is not None


def _strip_comments(source: str) -> str:
    """Drop leading `#` comment lines and blank-line separators."""
    lines = source.splitlines()
    # Skip leading comment + blank lines.
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or lines[i].strip() == ""):
        i += 1
    return "\n".join(lines[i:]).rstrip() + "\n"


# --- Drift-prevention: static shell files must match shellinit() output ---


@pytest.mark.parametrize("shell,path", [
    ("bash", BASH_WRAPPER),
    ("zsh", ZSH_WRAPPER),
    ("fish", FISH_WRAPPER),
])
def test_static_wrapper_matches_shellinit(shell: str, path: Path):
    """
    The committed shells/ctx.<shell> files must be byte-identical to
    what `ctx-bin shellinit <shell>` emits, ignoring a leading comment
    header on the static file.
    """
    static = _strip_comments(path.read_text())
    dynamic = shellinit(shell).rstrip() + "\n"
    assert static == dynamic, (
        f"{path} drifted from shellinit({shell!r}). Regenerate with:\n"
        f"  ctx-bin shellinit {shell} > {path}\n"
        f"(then re-add the leading comment header)"
    )


# --- bash integration ---


@pytest.mark.skipif(not _has("bash"), reason="bash not available")
def test_bash_static_file_applies_env_writeback(tmp_path: Path):
    (tmp_path / "context.yaml").write_text(
        "set-foo:\n"
        "  run:\n"
        "    - export FOO=bar-from-ctx\n"
    )
    script = f"""
        set -e
        source {BASH_WRAPPER}
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
def test_bash_shellinit_eval_applies_env_writeback(tmp_path: Path):
    """Same outcome as the static-file test but via `ctx-bin shellinit bash`."""
    (tmp_path / "context.yaml").write_text(
        "set-foo:\n"
        "  run:\n"
        "    - export FOO=bar-from-ctx\n"
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
        "bad:\n"
        "  run:\n"
        "    - export SHOULD_NOT_LEAK=1\n"
        "    - false\n"
    )
    script = f"""
        source {BASH_WRAPPER}
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


# --- zsh integration ---


@pytest.mark.skipif(not _has("zsh"), reason="zsh not available")
def test_zsh_static_file_applies_env_writeback(tmp_path: Path):
    (tmp_path / "context.yaml").write_text(
        "set-foo:\n"
        "  run:\n"
        "    - export FOO=bar-from-ctx\n"
    )
    script = f"""
        source {ZSH_WRAPPER}
        cd {tmp_path}
        ctx set-foo
        echo "AFTER_FOO=$FOO"
    """
    result = subprocess.run(
        ["zsh", "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ},
    )
    assert result.returncode == 0, result.stderr
    assert "AFTER_FOO=bar-from-ctx" in result.stdout


# --- fish integration ---


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_fish_static_file_applies_env_writeback(tmp_path: Path):
    (tmp_path / "context.yaml").write_text(
        "set-foo:\n"
        "  run:\n"
        "    - export FOO=bar-from-ctx\n"
    )
    script = f"""
        source {FISH_WRAPPER}
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


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_fish_shellinit_pipe_applies_env_writeback(tmp_path: Path):
    (tmp_path / "context.yaml").write_text(
        "set-foo:\n"
        "  run:\n"
        "    - export FOO=bar-from-ctx\n"
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
