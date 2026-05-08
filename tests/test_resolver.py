import pytest

from ctx.resolver import (
    GroupChild,
    GroupListing,
    LeafNode,
    ResolveError,
    resolve,
)


CONFIG = {
    "init": {"run": ["echo init"]},
    "build": {
        "prod": {
            "cwd": "./app",
            "export": {"FOO": "1"},
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
    assert result.export == {}


def test_resolve_multi_level_leaf():
    result = resolve(CONFIG, ["build", "prod"])
    assert isinstance(result, LeafNode)
    assert result.path == ("build", "prod")
    assert result.run == ["docker build ."]
    assert result.cwd == "./app"
    assert result.export == {"FOO": "1"}


def test_resolve_empty_tokens_lists_all_leaves_flattened():
    result = resolve(CONFIG, [])
    assert isinstance(result, GroupListing)
    assert result.path == ()
    # Flattens: "build" is a group so its leaves appear as
    # "build dev" and "build prod". `init` is a leaf at the top.
    assert [c.name for c in result.children] == [
        "build dev",
        "build prod",
        "init",
    ]
    assert all(c.desc is None for c in result.children)


def test_resolve_group_without_enough_tokens_lists_children():
    result = resolve(CONFIG, ["build"])
    assert isinstance(result, GroupListing)
    assert result.path == ("build",)
    # Relative to `build`, so no "build " prefix on the names.
    assert [c.name for c in result.children] == ["dev", "prod"]


def test_resolve_listing_flattens_deeper_groups_and_carries_desc():
    config = {
        "init": {"desc": "Install deps", "run": ["uv sync"]},
        "build": {"run": ["make"]},
        "deploy": {
            "prod": {
                "desc": "Prod deploy",
                "run": ["kubectl apply -f ."],
            },
            "staging": {"run": ["kubectl apply -f staging"]},
        },
    }
    result = resolve(config, [])
    assert isinstance(result, GroupListing)
    by_name = {c.name: c for c in result.children}
    # All leaves flattened, group names absent.
    assert set(by_name) == {"build", "deploy prod", "deploy staging", "init"}
    assert by_name["init"].desc == "Install deps"
    assert by_name["deploy prod"].desc == "Prod deploy"
    assert by_name["build"].desc is None
    assert by_name["deploy staging"].desc is None
    # Deterministic (sorted) order.
    assert [c.name for c in result.children] == [
        "build",
        "deploy prod",
        "deploy staging",
        "init",
    ]


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


CONFIG_WITH_ARGS = {
    "test": {"run": ["pytest {args}"]},
    "grep_with_default": {"run": ["rg {args|--color=always}"]},
    "plain": {"run": ["echo plain"]},
}


def test_resolve_args_captured_on_leaf_with_placeholder():
    result = resolve(CONFIG_WITH_ARGS, ["test", "-k", "login", "-x"])
    assert isinstance(result, LeafNode)
    assert result.path == ("test",)
    assert result.args == ["-k", "login", "-x"]
    assert result.accepts_args is True


def test_resolve_args_empty_on_leaf_with_placeholder_and_no_extra_tokens():
    result = resolve(CONFIG_WITH_ARGS, ["test"])
    assert isinstance(result, LeafNode)
    assert result.args == []
    assert result.accepts_args is True


def test_resolve_leaf_with_default_args_detected():
    result = resolve(CONFIG_WITH_ARGS, ["grep_with_default"])
    assert isinstance(result, LeafNode)
    assert result.accepts_args is True


def test_resolve_extra_tokens_still_error_when_no_placeholder():
    with pytest.raises(ResolveError) as exc:
        resolve(CONFIG_WITH_ARGS, ["plain", "extra"])
    assert "takes no further arguments" in str(exc.value)


def test_resolve_mode_defaults_to_source():
    result = resolve({"x": {"run": ["echo"]}}, ["x"])
    assert isinstance(result, LeafNode)
    assert result.mode == "source"


def test_resolve_mode_subprocess_propagates_from_yaml():
    result = resolve({"x": {"mode": "subprocess", "run": ["echo"]}}, ["x"])
    assert isinstance(result, LeafNode)
    assert result.mode == "subprocess"
