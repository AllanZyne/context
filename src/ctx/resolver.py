import re
from dataclasses import dataclass, field


class ResolveError(Exception):
    """Argv did not resolve to a valid command."""


ARGS_PLACEHOLDER = "{args}"
_ARGS_RE = re.compile(r"\{args(?:\|[^{}]*)?\}")


@dataclass(frozen=True)
class LeafNode:
    path: tuple[str, ...]
    run: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    export: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)
    source_rc: bool = False

    @property
    def accepts_args(self) -> bool:
        return any(_ARGS_RE.search(cmd) for cmd in self.run)


@dataclass(frozen=True)
class GroupChild:
    """One runnable leaf reachable from a GroupListing. `name` is the
    space-joined path RELATIVE to the listing's group — exactly what
    the user would type after `ctx` (or after the tokens that led to
    this listing). `desc` is the leaf's desc or None."""
    name: str
    desc: str | None


@dataclass(frozen=True)
class GroupListing:
    """Returned when tokens are exhausted at a group node (or with no tokens).
    Contains every leaf reachable from here, flattened — cli.py renders
    one line per leaf so the user sees a complete list of runnable
    commands in one view."""
    path: tuple[str, ...]
    children: list[GroupChild]


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
            # Extra tokens after a leaf: either consumed as {args} or an error.
            extra = list(tokens[i:])
            leaf = _as_leaf(node, path, args=extra)
            if leaf.accepts_args:
                return leaf
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
        return _as_leaf(node, path, args=[])
    return GroupListing(path=path, children=_list_children(node))


def _list_children(group: dict) -> list[GroupChild]:
    """Recursively flatten a group into all its runnable leaves.

    Each entry's `name` is the space-joined relative path from `group`
    down to the leaf — exactly what the user would type after the
    tokens that led to this listing.
    """
    result: list[GroupChild] = []
    for key in sorted(group.keys()):
        child = group[key]
        for sub_path, leaf in _walk_leaves(child, (key,)):
            result.append(
                GroupChild(
                    name=" ".join(sub_path),
                    desc=leaf.get("desc"),
                )
            )
    return result


def _walk_leaves(node: dict, prefix: tuple[str, ...]):
    """Yield (path, leaf_dict) for every leaf under `node`. Groups are
    descended into in sorted order; leaves terminate the recursion."""
    if _is_leaf(node):
        yield prefix, node
        return
    for key in sorted(node.keys()):
        yield from _walk_leaves(node[key], prefix + (key,))


def _is_leaf(node: dict) -> bool:
    return isinstance(node, dict) and "run" in node


def _as_leaf(node: dict, path: tuple[str, ...], args: list[str]) -> LeafNode:
    return LeafNode(
        path=path,
        run=list(node["run"]),
        cwd=node.get("cwd"),
        env=dict(node.get("env", {})),
        export=dict(node.get("export", {})),
        args=list(args),
        source_rc=bool(node.get("source_rc", False)),
    )
