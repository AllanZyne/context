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
