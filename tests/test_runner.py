import os
import subprocess
from pathlib import Path

import pytest

from ctx.resolver import LeafNode
from ctx.runner import run_leaf, RunnerError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Most tests just need a directory that exists.
    return tmp_path


def test_run_leaf_simple_echo_succeeds(project: Path, capfd):
    leaf = LeafNode(path=("x",), run=["echo hello-world"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "hello-world" in out
    # Command echo line should be present too.
    assert "$ echo hello-world" in out


def test_run_leaf_failure_returns_nonzero(project: Path):
    leaf = LeafNode(path=("x",), run=["false"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc != 0


def test_run_leaf_stops_on_first_failure(project: Path, capfd):
    leaf = LeafNode(path=("x",), run=["false", "echo should-not-run"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc != 0
    out = capfd.readouterr().out
    assert "should-not-run" not in out


def test_run_leaf_respects_cwd(project: Path, capfd):
    sub = project / "sub"
    sub.mkdir()
    leaf = LeafNode(path=("x",), run=["pwd"], cwd="sub")
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert str(sub.resolve()) in capfd.readouterr().out


def test_run_leaf_missing_cwd_errors_without_subprocess(project: Path):
    leaf = LeafNode(path=("x",), run=["echo"], cwd="nope")
    with pytest.raises(RunnerError) as exc:
        run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert "cwd does not exist" in str(exc.value)


def test_run_leaf_leaf_env_visible_to_command(project: Path, capfd):
    leaf = LeafNode(
        path=("x",),
        run=["sh -c 'echo FOO=$FOO'"],
        env={"FOO": "bar"},
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert "FOO=bar" in capfd.readouterr().out


def test_run_leaf_writes_env_dump_on_success(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"  # wrapper used mktemp -u: path does not exist
    leaf = LeafNode(path=("x",), run=["export NEW_VAR=42"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    assert dump.exists()
    assert "export NEW_VAR=$'42'" in dump.read_text()


def test_run_leaf_no_dump_when_env_unchanged(project: Path, tmp_path: Path):
    """Success with zero env diff must leave the dump path non-existent."""
    dump = tmp_path / "dump.sh"  # does not exist
    leaf = LeafNode(path=("x",), run=["echo no-env-change"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    assert not dump.exists()


def test_run_leaf_no_dump_on_failure(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"  # does not exist (mktemp -u)
    leaf = LeafNode(path=("x",), run=["export NEW_VAR=42", "false"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc != 0
    assert not dump.exists()


def test_run_leaf_fish_dump_uses_fish_syntax(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.fish"
    leaf = LeafNode(path=("x",), run=["export FISH_VAR=42"])
    rc = run_leaf(leaf, project, shell="fish", env_dump_path=dump)
    assert rc == 0
    assert dump.exists()
    assert "set -gx FISH_VAR '42'" in dump.read_text()


# --- export: values flow back to parent, env: values don't ---


def test_run_leaf_export_is_written_back_unchanged(project: Path, tmp_path: Path):
    """A variable declared in `export` must appear in the dump even if
    no command mutates it."""
    dump = tmp_path / "dump.sh"
    leaf = LeafNode(
        path=("x",),
        run=["echo just-printing"],
        export={"MY_EXPORT": "exported-value"},
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    assert dump.exists()
    assert "export MY_EXPORT=$'exported-value'" in dump.read_text()


def test_run_leaf_env_is_not_written_back_when_unchanged(project: Path, tmp_path: Path):
    """A variable declared only in `env` must NOT appear in the dump
    if the command doesn't mutate it."""
    dump = tmp_path / "dump.sh"
    leaf = LeafNode(
        path=("x",),
        run=["echo just-printing"],
        env={"MY_ENV": "env-value"},
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    # Empty diff → dump file not created at all.
    assert not dump.exists()


def test_run_leaf_export_and_env_visible_to_commands(project: Path, capfd):
    leaf = LeafNode(
        path=("x",),
        run=['echo "E=$E X=$X"'],
        env={"E": "env-val"},
        export={"X": "exp-val"},
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "E=env-val X=exp-val" in out


# --- {args} substitution ---


def test_run_leaf_args_substituted_into_command(project: Path, capfd):
    leaf = LeafNode(
        path=("test",),
        run=["echo {args}"],
        args=["hello", "world"],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "hello world" in out


def test_run_leaf_args_shell_quoting(project: Path, capfd):
    """Args with spaces/quotes must survive the substitution."""
    leaf = LeafNode(
        path=("test",),
        run=["printf '%s\\n' {args}"],
        args=["first", "second with spaces", "third'quote"],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    lines = capfd.readouterr().out.splitlines()
    # Each arg should end up as one printf argument.
    assert "first" in lines
    assert "second with spaces" in lines
    assert "third'quote" in lines


def test_run_leaf_args_placeholder_with_empty_args(project: Path, capfd):
    leaf = LeafNode(
        path=("test",),
        run=["echo before{args}after"],
        args=[],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert "beforeafter" in capfd.readouterr().out


def test_run_leaf_default_args_used_when_empty(project: Path, capfd):
    leaf = LeafNode(
        path=("test",),
        run=["echo {args|default-value}"],
        args=[],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    assert "default-value" in capfd.readouterr().out


def test_run_leaf_default_args_overridden_when_provided(project: Path, capfd):
    leaf = LeafNode(
        path=("test",),
        run=["echo {args|fallback}"],
        args=["actual"],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "actual" in out
    assert "fallback" not in out


def test_run_leaf_args_substituted_in_multiple_commands(project: Path, capfd):
    leaf = LeafNode(
        path=("test",),
        run=[
            "echo first {args}",
            "echo second {args}",
        ],
        args=["X"],
    )
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=None)
    assert rc == 0
    out = capfd.readouterr().out
    assert "first X" in out
    assert "second X" in out
