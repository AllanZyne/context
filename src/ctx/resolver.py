from dataclasses import dataclass, field


class ResolveError(Exception):
    """Argv did not resolve to a valid command."""


@dataclass(frozen=True)
class LeafNode:
    path: tuple[str, ...]
    run: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GroupListing:
    """Returned when tokens are exhausted at a group node (or with no tokens).
    cli.py uses this to print a list of valid subcommands and exit 0."""
    path: tuple[str, ...]
    children: list[str]


def resolve(data: dict, tokens: list[str]) -> LeafNode | GroupListing:
    """
    Walk the command tree using tokens. Returns either a LeafNode for
    execution or a GroupListing when the user needs more arguments.
    Raises ResolveError for bad paths.

    Assumes `data` has already been validated by config.load_and_validate.
    """
    node = data
    path: tuple[str, ...] = ()

    for i, token in enumerate(tokens):
        if _is_leaf(node):
            leaf = _as_leaf(node, path)
            extra = tokens[i:]
            raise ResolveError(
                f"command {' '.join(path)!r} takes no further arguments "
                f"(got {extra[0]!r})"
            )
        if token not in node:
            valid = sorted(node.keys())
            under = ".".join(path) or "<root>"
            raise ResolveError(
                f"unknown subcommand {token!r} under {under}. "
                f"Valid: {', '.join(valid)}"
            )
        node = node[token]
        path = path + (token,)

    if _is_leaf(node):
        return _as_leaf(node, path)
    return GroupListing(path=path, children=sorted(node.keys()))


def _is_leaf(node: dict) -> bool:
    return isinstance(node, dict) and "run" in node


def _as_leaf(node: dict, path: tuple[str, ...]) -> LeafNode:
    return LeafNode(
        path=path,
        run=list(node["run"]),
        cwd=node.get("cwd"),
        env=dict(node.get("env", {})),
    )
