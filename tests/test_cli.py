from pathlib import Path

from ctx.cli import main


def _write_yaml(dirpath: Path, body: str) -> None:
    (dirpath / "context.yaml").write_text(body)


def test_shellinit_bash_does_not_require_yaml(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no context.yaml here
    rc = main(["shellinit", "bash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ctx()" in out
    assert "--shell=bash" in out


def test_shellinit_fish(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["shellinit", "fish"])
    assert rc == 0
    assert "function ctx" in capsys.readouterr().out


def test_shellinit_unknown_shell(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["shellinit", "perl"])
    assert rc == 1
    assert "ctx:" in capsys.readouterr().err


def test_runs_leaf_successfully(tmp_path, monkeypatch, capfd):
    _write_yaml(tmp_path, """
init:
  run:
    - echo hi-from-ctx
""")
    monkeypatch.chdir(tmp_path)
    rc = main(["init"])
    assert rc == 0
    assert "hi-from-ctx" in capfd.readouterr().out


def test_missing_yaml_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["init"])
    assert rc == 1
    assert "no context.yaml found" in capsys.readouterr().err


def test_unknown_subcommand_exits_2(tmp_path, monkeypatch, capsys):
    _write_yaml(tmp_path, """
build:
  prod:
    run:
      - echo
""")
    monkeypatch.chdir(tmp_path)
    rc = main(["build", "staging"])
    assert rc == 2
    assert "unknown subcommand" in capsys.readouterr().err


def test_group_with_exhausted_tokens_lists_children(
    tmp_path, monkeypatch, capsys
):
    _write_yaml(tmp_path, """
build:
  prod: {run: [echo p]}
  dev: {run: [echo d]}
""")
    monkeypatch.chdir(tmp_path)
    rc = main(["build"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "prod" in out and "dev" in out


def test_bare_ctx_lists_all_leaves_flattened(tmp_path, monkeypatch, capsys):
    _write_yaml(tmp_path, """
init:
  desc: Install project dependencies
  run:
    - uv sync
build:
  run:
    - make
deploy:
  prod:
    desc: Production deploy
    run:
      - kubectl apply -f .
  staging:
    run:
      - kubectl apply -f staging
""")
    monkeypatch.chdir(tmp_path)
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()

    assert lines[0] == "Available subcommands:"

    entries = [l.strip() for l in lines[1:] if l.strip()]
    # All leaves listed, nested ones shown with space-joined paths,
    # sorted alphabetically. Groups (`deploy`) do not appear alone.
    assert entries[0] == "build"
    assert entries[1].startswith("deploy prod")
    assert "Production deploy" in entries[1]
    assert entries[2] == "deploy staging"
    assert entries[3].startswith("init")
    assert "Install project dependencies" in entries[3]
    assert len(entries) == 4  # no group-only lines


def test_shell_flag_propagated_to_runner_source_mode(tmp_path, monkeypatch):
    """With --shell=fish (default source mode), the emitted script
    should use fish syntax."""
    _write_yaml(tmp_path, """
x:
  run:
    - set -gx FISH_TEST 1
""")
    script = tmp_path / "s.fish"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CTX_SOURCE_SCRIPT", str(script))
    rc = main(["--shell=fish", "x"])
    assert rc == 0
    text = script.read_text()
    # fish single-quoted path and set -l _ctx_prev_pwd (fish builder hallmark)
    assert "_ctx_prev_pwd" in text
    assert "set -gx FISH_TEST 1" in text


def test_subprocess_mode_env_dump_uses_shell_flag(tmp_path, monkeypatch):
    """With mode: subprocess and --shell=fish, the env-dump file uses
    fish syntax — confirms the flag threads through both modes."""
    _write_yaml(tmp_path, """
x:
  mode: subprocess
  run:
    - export FISH_TEST=1
""")
    dump = tmp_path / "dump.fish"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CTX_ENV_DUMP", str(dump))
    rc = main(["--shell=fish", "x"])
    assert rc == 0
    assert "set -gx FISH_TEST" in dump.read_text()


def test_invalid_shell_flag_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["--shell=powershell", "shellinit", "bash"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unsupported --shell" in err
    assert "powershell" in err


def test_shellinit_reserved_shadows_user_command(tmp_path, monkeypatch, capsys):
    _write_yaml(tmp_path, """
shellinit:
  run:
    - echo user-version
""")
    monkeypatch.chdir(tmp_path)
    rc = main(["shellinit", "bash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ctx()" in out
    assert "user-version" not in out


def test_args_forwarded_to_leaf(tmp_path, monkeypatch, capfd):
    _write_yaml(tmp_path, """
greet:
  run:
    - echo hi {args}
""")
    monkeypatch.chdir(tmp_path)
    rc = main(["greet", "there", "friend"])
    assert rc == 0
    assert "hi there friend" in capfd.readouterr().out


def test_args_default_kicks_in_with_no_extra_tokens(tmp_path, monkeypatch, capfd):
    _write_yaml(tmp_path, """
greet:
  run:
    - echo {args|world}
""")
    monkeypatch.chdir(tmp_path)
    rc = main(["greet"])
    assert rc == 0
    assert "world" in capfd.readouterr().out
