import os
import sys
from pathlib import Path

from ctx.config import ConfigError, find_yaml, load_and_validate
from ctx.resolver import (
    GroupListing,
    LeafNode,
    ResolveError,
    resolve,
)
from ctx.runner import RunnerError, run_leaf
from ctx.shellinit import SUPPORTED_SHELLS, shellinit


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        shell, argv = _extract_shell_flag(argv)
    except ValueError as e:
        return _die(str(e))

    # Reserved builtin: shellinit. Dispatched before touching YAML.
    if argv and argv[0] == "shellinit":
        return _cmd_shellinit(argv[1:])

    # From here on we need a context.yaml.
    try:
        yaml_path = find_yaml(Path.cwd())
        data = load_and_validate(yaml_path)
    except ConfigError as e:
        return _die(str(e))

    try:
        result = resolve(data, argv)
    except ResolveError as e:
        print(f"ctx: {e}", file=sys.stderr)
        return 2

    if isinstance(result, GroupListing):
        _print_group(result)
        return 0

    assert isinstance(result, LeafNode)
    env_dump = os.environ.get("CTX_ENV_DUMP")
    env_dump_path = Path(env_dump) if env_dump else None

    try:
        return run_leaf(
            result,
            project_root=yaml_path.parent,
            shell=shell,
            env_dump_path=env_dump_path,
        )
    except RunnerError as e:
        return _die(str(e))


def _extract_shell_flag(argv: list[str]) -> tuple[str, list[str]]:
    """Pull --shell=<x> out of argv (if present). Default: bash."""
    shell = "bash"
    rest: list[str] = []
    for arg in argv:
        if arg.startswith("--shell="):
            shell = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(
            f"unsupported --shell={shell!r}; expected one of {SUPPORTED_SHELLS}"
        )
    return shell, rest


def _cmd_shellinit(args: list[str]) -> int:
    if len(args) != 1:
        return _die("usage: ctx-bin shellinit <bash|zsh|fish>")
    try:
        print(shellinit(args[0]), end="")
    except ValueError as e:
        return _die(str(e))
    return 0


def _print_group(result: GroupListing) -> None:
    where = ".".join(result.path) if result.path else "<root>"
    print(f"Available subcommands under {where}:")
    for name in result.children:
        print(f"  {name}")


def _die(msg: str) -> int:
    print(f"ctx: {msg}", file=sys.stderr)
    return 1
