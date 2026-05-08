from pathlib import Path

import pytest

from ctx.config import find_yaml, ConfigError


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("commands: {}\n")
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


from ctx.config import load_and_validate


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "context.yaml"
    p.write_text(body)
    return p


def test_load_minimal_leaf(tmp_path: Path):
    _write(tmp_path, """
commands:
  init:
    run:
      - echo hello
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["commands"]["init"]["run"] == ["echo hello"]


def test_load_nested(tmp_path: Path):
    _write(tmp_path, """
commands:
  build:
    prod:
      cwd: ./app
      env:
        NODE_ENV: production
      run:
        - docker build .
""")
    data = load_and_validate(tmp_path / "context.yaml")
    leaf = data["commands"]["build"]["prod"]
    assert leaf["cwd"] == "./app"
    assert leaf["env"] == {"NODE_ENV": "production"}
    assert leaf["run"] == ["docker build ."]


@pytest.mark.parametrize("body,needle", [
    ("", "top-level 'commands'"),
    ("commands: []", "non-empty mapping"),
    ("commands: {}", "non-empty mapping"),
    ("""
commands:
  build:
    run:
      - make
    prod:
      run:
        - make prod
""", "unexpected key"),
    ("""
commands:
  empty:
    desc: nothing
""", "empty node"),
    ("""
commands:
  build:
    run: make
""", "non-empty list"),
    ("""
commands:
  build:
    run: []
""", "non-empty list"),
    ("""
commands:
  build:
    run:
      - ""
""", "non-empty string"),
    ("""
commands:
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
commands:
  x:
    env:
      N: 1
      B: true
    run:
      - echo
""")
    data = load_and_validate(tmp_path / "context.yaml")
    assert data["commands"]["x"]["env"] == {"N": "1", "B": "True"}
