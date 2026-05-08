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
    assert outer.exists()  # sanity: both exist


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


def test_load_nested(tmp_path: Path):
    _write(tmp_path, """
build:
  prod:
    cwd: ./app
    env:
      NODE_ENV: production
    run:
      - docker build .
""")
    data = load_and_validate(tmp_path / "context.yaml")
    leaf = data["build"]["prod"]
    assert leaf["cwd"] == "./app"
    assert leaf["env"] == {"NODE_ENV": "production"}
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
  run: make
""", "non-empty list"),
    ("""
build:
  run: []
""", "non-empty list"),
    ("""
build:
  run:
    - ""
""", "non-empty string"),
    ("""
build:
  run:
    - make
  env:
    FOO: [1, 2]
""", "scalar"),
])
def test_validation_errors(tmp_path: Path, body: str, needle: str):
    _write(tmp_path, body)
    with pytest.raises(ConfigError) as exc:
        load_and_validate(tmp_path / "context.yaml")
    assert needle in str(exc.value)


def test_env_values_coerced_to_strings(tmp_path: Path):
    _write(tmp_path, """
x:
  env:
    N: 1
    B: true
  run:
    - echo
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["x"]["env"] == {"N": "1", "B": "True"}
