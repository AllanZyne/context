from pathlib import Path

import pytest

from ctx.config import find_yaml, ConfigError, load_and_validate


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("init:\n  run:\n    - echo\n")
    return path


def test_find_yaml_in_start_directory(tmp_path: Path):
    yaml = _touch(tmp_path / "context.yaml")
    assert find_yaml(tmp_path) == yaml


def test_find_yaml_several_levels_up(tmp_path: Path):
    yaml = _touch(tmp_path / "context.yaml")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_yaml(deep) == yaml


def test_find_yaml_stops_at_first_match(tmp_path: Path):
    outer = _touch(tmp_path / "context.yaml")
    inner = _touch(tmp_path / "proj" / "context.yaml")
    assert find_yaml(tmp_path / "proj" / "src") == inner
    assert outer.exists()


def test_find_yaml_missing_raises(tmp_path: Path):
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    with pytest.raises(ConfigError) as exc:
        find_yaml(deep)
    assert "no context.yaml found" in str(exc.value)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "context.yaml"
    p.write_text(body)
    return p


def test_load_minimal_leaf(tmp_path: Path):
    _write(tmp_path, """
init:
  run:
    - echo hello
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["init"]["run"] == ["echo hello"]


def test_load_scalar_run_coerced_to_list(tmp_path: Path):
    _write(tmp_path, """
init:
  run: echo hello
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["init"]["run"] == ["echo hello"]


def test_load_nested(tmp_path: Path):
    _write(tmp_path, """
build:
  prod:
    cwd: ./app
    export:
      NODE_ENV: production
    run:
      - docker build .
""")
    data = load_and_validate(tmp_path / "context.yaml")
    leaf = data["build"]["prod"]
    assert leaf["cwd"] == "./app"
    assert leaf["export"] == {"NODE_ENV": "production"}
    assert leaf["run"] == ["docker build ."]


@pytest.mark.parametrize("body,needle", [
    ("", "non-empty mapping"),
    ("[]", "non-empty mapping"),
    ("{}", "non-empty mapping"),
    ("""
build:
  run:
    - make
  prod:
    run:
      - make prod
""", "unexpected key"),
    ("""
empty:
  desc: nothing
""", "empty node"),
    ("""
build:
  run: []
""", "non-empty string or list"),
    ("""
build:
  run: ""
""", "non-empty string"),
    ("""
build:
  run: 42
""", "non-empty string or list"),
    ("""
build:
  run:
    - ""
""", "non-empty string"),
    ("""
build:
  run:
    - make
  export:
    FOO: [1, 2]
""", "scalar"),
    ("""
build:
  run:
    - make
  mode: weird
""", "must be one of"),
])
def test_validation_errors(tmp_path: Path, body: str, needle: str):
    _write(tmp_path, body)
    with pytest.raises(ConfigError) as exc:
        load_and_validate(tmp_path / "context.yaml")
    assert needle in str(exc.value)


def test_export_values_coerced_to_strings(tmp_path: Path):
    _write(tmp_path, """
x:
  export:
    MYVAR: hello
    N: 42
    B: true
  run:
    - echo
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["x"]["export"] == {"MYVAR": "hello", "N": "42", "B": "True"}


def test_export_wrong_type_rejected(tmp_path: Path):
    _write(tmp_path, """
x:
  export:
    FOO: [1, 2]
  run:
    - echo
""")
    with pytest.raises(ConfigError) as exc:
        load_and_validate(tmp_path / "context.yaml")
    assert "scalar" in str(exc.value)


def test_mode_defaults_to_absent(tmp_path: Path):
    """mode is optional in yaml; resolver applies the default."""
    _write(tmp_path, """
x:
  run:
    - echo
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert "mode" not in data["x"]


def test_mode_accepts_source_and_subprocess(tmp_path: Path):
    _write(tmp_path, """
a:
  mode: source
  run:
    - echo
b:
  mode: subprocess
  run:
    - echo
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["a"]["mode"] == "source"
    assert data["b"]["mode"] == "subprocess"
