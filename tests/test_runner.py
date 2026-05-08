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
    dump = tmp_path / "dump.sh"
    leaf = LeafNode(path=("x",), run=["export NEW_VAR=42"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc == 0
    content = dump.read_text()
    assert "export NEW_VAR=$'42'" in content


def test_run_leaf_dump_file_empty_on_failure(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.sh"
    dump.write_text("")  # wrapper would create it empty
    leaf = LeafNode(path=("x",), run=["export NEW_VAR=42", "false"])
    rc = run_leaf(leaf, project, shell="bash", env_dump_path=dump)
    assert rc != 0
    assert dump.read_text() == ""


def test_run_leaf_fish_dump_uses_fish_syntax(project: Path, tmp_path: Path):
    dump = tmp_path / "dump.fish"
    leaf = LeafNode(path=("x",), run=["export FISH_VAR=42"])
    rc = run_leaf(leaf, project, shell="fish", env_dump_path=dump)
    assert rc == 0
    assert "set -gx FISH_VAR '42'" in dump.read_text()
