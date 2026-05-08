import pytest

from ctx.resolver import resolve, LeafNode, GroupListing, ResolveError


CONFIG = {
    "init": {"run": ["echo init"]},
    "build": {
        "prod": {
            "cwd": "./app",
            "env": {"FOO": "1"},
            "run": ["docker build ."],
        },
        "dev": {"run": ["docker build -t dev ."]},
    },
}


def test_resolve_single_level_leaf():
    result = resolve(CONFIG, ["init"])
    assert isinstance(result, LeafNode)
    assert result.path == ("init",)
    assert result.run == ["echo init"]
    assert result.cwd is None
    assert result.env == {}


def test_resolve_multi_level_leaf():
    result = resolve(CONFIG, ["build", "prod"])
    assert isinstance(result, LeafNode)
    assert result.path == ("build", "prod")
    assert result.run == ["docker build ."]
    assert result.cwd == "./app"
    assert result.env == {"FOO": "1"}


def test_resolve_empty_tokens_lists_top_level():
    result = resolve(CONFIG, [])
    assert isinstance(result, GroupListing)
    assert result.path == ()
    assert sorted(result.children) == ["build", "init"]


def test_resolve_group_without_enough_tokens_lists_children():
    result = resolve(CONFIG, ["build"])
    assert isinstance(result, GroupListing)
    assert result.path == ("build",)
    assert sorted(result.children) == ["dev", "prod"]


def test_resolve_unknown_subcommand():
    with pytest.raises(ResolveError) as exc:
        resolve(CONFIG, ["build", "staging"])
    msg = str(exc.value)
    assert "unknown subcommand 'staging'" in msg
    assert "build" in msg
    assert "prod" in msg and "dev" in msg


def test_resolve_extra_tokens_on_leaf():
    with pytest.raises(ResolveError) as exc:
        resolve(CONFIG, ["init", "extra"])
    assert "takes no further arguments" in str(exc.value)
    assert "'extra'" in str(exc.value)
