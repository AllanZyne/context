import shutil
import subprocess
from pathlib import Path

import pytest

from ctx.resolver import LeafNode
from ctx.runner import run_leaf, RunnerError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _has(binary: str) -> bool:
    return shutil.which(binary) is not None


# =====================================================================
# Source mode (default): ctx-bin writes a script, the wrapper sources it.
# We simulate the wrapper here by invoking a real shell to source the
# generated file and then inspect its effect.
# =====================================================================


def _run_and_capture_via_bash(
    project: Path,
    leaf: LeafNode,
    extra: str = "",
) -> tuple[int, str]:
    """Invoke run_leaf in source mode, then `source` the emitted script
    under a fresh bash and return (rc, combined_output). `extra` is any
    shell code to run after sourcing so we can inspect env/cwd."""
    script_path = project / "emitted.sh"
    rc_runner = run_leaf(
        leaf,
        project,
        shell="bash",
        env_dump_path=None,
        source_script_path=script_path,
    )
    assert rc_runner == 0
    assert script_path.exists(), "source mode must write the script file"
    driver = f"""
        set +e
        . {script_path}
        _rc=$?
        {extra}
        exit $_rc
    """
    r = subprocess.run(["bash", "-c", driver], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_source_mode_default(project: Path):
    """When mode is unset it's source by default, and the runner
    produces a script (not a subprocess execution)."""
    leaf = LeafNode(path=("x",), run=["echo from-script"])
    script = project / "s.sh"
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None,
                  source_script_path=script)
    assert rc == 0
    assert script.exists()
    text = script.read_text()
    assert "echo from-script" in text


def test_source_mode_script_echoes_and_runs(project: Path):
    leaf = LeafNode(path=("x",), run=["echo hello-world"])
    rc, out = _run_and_capture_via_bash(project, leaf)
    assert rc == 0
    assert "hello-world" in out
    assert "$ echo hello-world" in out


def test_source_mode_export_flows_to_parent_shell(project: Path):
    leaf = LeafNode(
        path=("x",),
        run=["true"],
        export={"MY_EXPORT": "exported-value"},
    )
    rc, out = _run_and_capture_via_bash(
        project, leaf, extra='echo "X=${MY_EXPORT:-unset}"'
    )
    assert rc == 0
    assert "X=exported-value" in out


def test_source_mode_command_mutations_flow_through(project: Path):
    leaf = LeafNode(path=("x",), run=["export NEW_VAR=42"])
    rc, out = _run_and_capture_via_bash(
        project, leaf, extra='echo "N=${NEW_VAR:-unset}"'
    )
    assert rc == 0
    assert "N=42" in out


def test_source_mode_cwd_applied_but_restored(project: Path):
    sub = project / "sub"
    sub.mkdir()
    leaf = LeafNode(path=("x",), run=["pwd"], cwd="sub")
    rc, out = _run_and_capture_via_bash(project, leaf, extra='echo "FINAL=$PWD"')
    assert rc == 0
    assert str(sub.resolve()) in out
    # After sourcing, pwd is back to the driver's starting dir.
    assert f"FINAL={str(sub.resolve())}" not in out


def test_source_mode_stops_on_first_failure(project: Path):
    leaf = LeafNode(path=("x",), run=["false", "echo should-not-run"])
    rc, out = _run_and_capture_via_bash(project, leaf)
    assert rc != 0
    assert "should-not-run" not in out


def test_source_mode_missing_cwd_errors(project: Path):
    leaf = LeafNode(path=("x",), run=["echo"], cwd="nope")
    with pytest.raises(RunnerError) as exc:
        run_leaf(
            leaf, project, shell="bash", env_dump_path=None,
            source_script_path=project / "s.sh",
        )
    assert "cwd does not exist" in str(exc.value)


def test_source_mode_args_substituted(project: Path):
    leaf = LeafNode(
        path=("t",),
        run=["echo {args}"],
        args=["alpha", "beta gamma"],
    )
    rc, out = _run_and_capture_via_bash(project, leaf)
    assert rc == 0
    assert "alpha 'beta gamma'" in out or "alpha beta gamma" in out


def test_source_mode_degrades_to_subprocess_without_wrapper(project: Path, capfd):
    """When no source_script_path is given (user runs ctx-bin bare),
    commands still execute so the user sees output."""
    leaf = LeafNode(path=("x",), run=["echo bare-run"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None,
                  source_script_path=None)
    assert rc == 0
    assert "bare-run" in capfd.readouterr().out


# --- fish source-mode ---


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_source_mode_fish_runs_fish_syntax(project: Path):
    leaf = LeafNode(
        path=("x",),
        run=["set -l greet hi", "echo greeting=$greet"],
    )
    script = project / "s.fish"
    rc = run_leaf(leaf, project, shell="fish", env_dump_path=None,
                  source_script_path=script)
    assert rc == 0
    driver = f"source {script}"
    r = subprocess.run(["fish", "-c", driver], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "greeting=hi" in r.stdout


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_source_mode_fish_stops_on_failure(project: Path):
    leaf = LeafNode(path=("x",), run=["false", "echo should-not-run"])
    script = project / "s.fish"
    run_leaf(leaf, project, shell="fish", env_dump_path=None,
             source_script_path=script)
    # Execute under fish, capture return code
    r = subprocess.run(
        ["fish", "-c", f"source {script}"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "should-not-run" not in r.stdout


# =====================================================================
# Subprocess mode (opt-in): commands execute under a subprocess and env
# diff flows back via env_dump_path.
# =====================================================================


def _sub(**kw) -> LeafNode:
    kw.setdefault("mode", "subprocess")
    return LeafNode(**kw)


def test_subprocess_simple_echo(project: Path, capfd):
    leaf = _sub(path=("x",), run=["echo hello-world"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "hello-world" in out
    assert "$ echo hello-world" in out


def test_subprocess_failure_returns_nonzero(project: Path):
    leaf = _sub(path=("x",), run=["false"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc != 0


def test_subprocess_stops_on_first_failure(project: Path, capfd):
    leaf = _sub(path=("x",), run=["false", "echo should-not-run"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc != 0
    out = capfd.readouterr().out
    assert "should-not-run" not in out


def test_subprocess_respects_cwd(project: Path, capfd):
    sub = project / "sub"
    sub.mkdir()
    leaf = _sub(path=("x",), run=["pwd"], cwd="sub")
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert str(sub.resolve()) in capfd.readouterr().out


def test_subprocess_missing_cwd_errors_without_subprocess(project: Path):
    leaf = _sub(path=("x",), run=["echo"], cwd="nope")
    with pytest.raises(RunnerError) as exc:
        run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert "cwd does not exist" in str(exc.value)


def test_subprocess_writes_env_dump_on_success(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"
    leaf = _sub(path=("x",), run=["export NEW_VAR=42"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    assert dump.exists()
    assert "export NEW_VAR=$'42'" in dump.read_text()


def test_subprocess_no_dump_when_env_unchanged(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"
    leaf = _sub(path=("x",), run=["echo no-env-change"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    assert not dump.exists()


def test_subprocess_no_dump_on_failure(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"
    leaf = _sub(path=("x",), run=["export NEW_VAR=42", "false"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc != 0
    assert not dump.exists()


def test_subprocess_fish_dump_uses_fish_syntax(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.fish"
    leaf = _sub(path=("x",), run=["export FISH_VAR=42"])
    rc = run_leaf(leaf, project, shell="fish", env_dump_path=dump)
    assert rc == 0
    assert dump.exists()
    assert "set -gx FISH_VAR '42'" in dump.read_text()


def test_subprocess_export_written_back(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"
    leaf = _sub(
        path=("x",),
        run=["echo just-printing"],
        export={"MY_EXPORT": "exported-value"},
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    assert dump.exists()
    assert "export MY_EXPORT=$'exported-value'" in dump.read_text()


def test_subprocess_export_visible_to_commands(project: Path, capfd):
    leaf = _sub(
        path=("x",),
        run=['echo "X=$X"'],
        export={"X": "exp-val"},
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert "X=exp-val" in capfd.readouterr().out


# --- {args} in subprocess mode (same substitution code path) ---


def test_subprocess_args_substituted(project: Path, capfd):
    leaf = _sub(
        path=("test",),
        run=["echo {args}"],
        args=["hello", "world"],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert "hello world" in capfd.readouterr().out


def test_subprocess_args_shell_quoting(project: Path, capfd):
    leaf = _sub(
        path=("test",),
        run=["printf '%s\\n' {args}"],
        args=["first", "second with spaces", "third'quote"],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    lines = capfd.readouterr().out.splitlines()
    assert "first" in lines
    assert "second with spaces" in lines
    assert "third'quote" in lines


def test_subprocess_default_args_used_when_empty(project: Path, capfd):
    leaf = _sub(
        path=("test",),
        run=["echo {args|default-value}"],
        args=[],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert "default-value" in capfd.readouterr().out


# --- Per-shell execution in subprocess mode ---


@pytest.mark.skipif(not _has("zsh"), reason="zsh not available")
def test_subprocess_uses_zsh_when_shell_is_zsh(project: Path, capfd):
    leaf = _sub(path=("x",), run=['echo "zsh=${ZSH_VERSION:-absent}"'])
    rc = run_leaf(leaf, project, shell="zsh", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "zsh=" in out
    assert "zsh=absent" not in out


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_subprocess_uses_fish_when_shell_is_fish(project: Path, capfd):
    leaf = _sub(
        path=("x",),
        run=[
            "set -l greet hi",
            "echo greeting=$greet",
        ],
    )
    rc = run_leaf(leaf, project, shell="fish", env_dump_path=None)
    assert rc == 0
    assert "greeting=hi" in capfd.readouterr().out


@pytest.mark.skipif(not _has("fish"), reason="fish not available")
def test_subprocess_fish_fails_fast(project: Path, capfd):
    leaf = _sub(
        path=("x",),
        run=["false", "echo should-not-appear"],
    )
    rc = run_leaf(leaf, project, shell="fish", env_dump_path=None)
    assert rc != 0
    assert "should-not-appear" not in capfd.readouterr().out
