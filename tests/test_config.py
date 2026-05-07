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
