from pathlib import Path

YAML_NAME = "context.yaml"


class ConfigError(Exception):
    """Raised for any failure loading or validating context.yaml."""


def find_yaml(start: Path) -> Path:
    """
    Walk upward from `start` until a file named context.yaml is found.
    Raises ConfigError if the filesystem root is reached without a match.
    """
    start = start.resolve()
    current = start
    while True:
        candidate = current / YAML_NAME
        if candidate.is_file():
            return candidate
        if current.parent == current:
            raise ConfigError(
                f"no context.yaml found (searched from {start})"
            )
        current = current.parent


import yaml


_LEAF_KEYS = {"run", "desc", "cwd", "env"}


def load_and_validate(yaml_path: Path) -> dict:
    """
    Parse and validate context.yaml. Returns the parsed dict after
    coercing env values to strings. Raises ConfigError with a dotted
    node path on any schema violation.
    """
    try:
        raw = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"failed to parse {yaml_path}: {e}") from e

    if not isinstance(raw, dict) or not raw:
        raise ConfigError("context.yaml must be a non-empty mapping of commands")

    _validate_group(raw, path=())
    return raw


def _validate_group(group: dict, path: tuple[str, ...]) -> None:
    for name, node in group.items():
        _validate_node(node, path + (str(name),))


def _validate_node(node, path: tuple[str, ...]) -> None:
    dotted = ".".join(path) or "<root>"
    if not isinstance(node, dict):
        raise ConfigError(f"{dotted}: expected a mapping, got {type(node).__name__}")
    if not node:
        raise ConfigError(f"{dotted}: empty node (needs either 'run' or sub-commands)")

    if "run" in node:
        # Leaf node.
        extra = set(node) - _LEAF_KEYS
        if extra:
            raise ConfigError(
                f"{dotted}: leaf node has unexpected key(s) {sorted(extra)!r}; "
                "a node with 'run' cannot also have sub-commands"
            )
        _validate_leaf(node, path)
    else:
        # Check if this looks like a leaf (only has optional leaf keys but no 'run')
        leaf_only_keys = set(node) & (_LEAF_KEYS - {"run"})
        if leaf_only_keys and len(node) == len(leaf_only_keys):
            # Node has only optional leaf keys like 'desc' but no 'run'
            raise ConfigError(f"{dotted}: empty node (needs either 'run' or sub-commands)")
        # Group node: all keys are sub-command names.
        _validate_group(node, path)


def _validate_leaf(node: dict, path: tuple[str, ...]) -> None:
    dotted = ".".join(path) or "<root>"
    run = node["run"]
    if not isinstance(run, list) or not run:
        raise ConfigError(f"{dotted}: 'run' must be a non-empty list of strings")
    for i, cmd in enumerate(run):
        if not isinstance(cmd, str) or not cmd.strip():
            raise ConfigError(f"{dotted}.run[{i}]: expected a non-empty string")

    if "desc" in node and not isinstance(node["desc"], str):
        raise ConfigError(f"{dotted}.desc: must be a string")

    if "cwd" in node and not isinstance(node["cwd"], str):
        raise ConfigError(f"{dotted}.cwd: must be a string")

    if "env" in node:
        env = node["env"]
        if not isinstance(env, dict):
            raise ConfigError(f"{dotted}.env: must be a mapping")
        coerced = {}
        for k, v in env.items():
            if not isinstance(k, str):
                raise ConfigError(f"{dotted}.env: keys must be strings")
            if isinstance(v, (list, dict)):
                raise ConfigError(
                    f"{dotted}.env.{k}: value must be a scalar (got {type(v).__name__})"
                )
            coerced[k] = str(v)
        node["env"] = coerced
