import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from ctx.emit import diff_env, format_bash, format_fish
from ctx.resolver import LeafNode


class RunnerError(Exception):
    """Raised for pre-execution errors (bad cwd, etc.)."""


def run_leaf(
    leaf: LeafNode,
    project_root: Path,
    shell: str,
    env_dump_path: Path | None,
) -> int:
    """
    Execute all commands in `leaf.run` under a single bash subprocess.

    If `env_dump_path` is given, writes the env writeback source (in
    `shell` syntax) to it on success. On failure the file is left
    untouched (caller is expected to have it empty or non-existent so
    that shell wrappers skip sourcing).
    """
    cwd = _resolve_cwd(project_root, leaf.cwd)
    initial_env = os.environ.copy()
    initial_env.update(leaf.env)

    # Tempfile for bash to dump env -0 into.
    with tempfile.NamedTemporaryFile(
        prefix="ctx-raw-env-", delete=False
    ) as tmp:
        raw_env_path = Path(tmp.name)

    try:
        script = _build_bash_script(leaf.run, cwd, raw_env_path)
        completed = subprocess.run(
            ["bash", "-c", script],
            env=initial_env,
            cwd=cwd,
        )
        rc = completed.returncode

        if rc == 0 and env_dump_path is not None:
            final_env = _parse_env_nul(raw_env_path.read_bytes())
            added, removed = diff_env(initial_env, final_env)
            source = _format_for_shell(shell, added, removed)
            env_dump_path.write_text(source)

        return rc
    finally:
        try:
            raw_env_path.unlink()
        except FileNotFoundError:
            pass


def _resolve_cwd(project_root: Path, cwd: str | None) -> Path:
    target = project_root if cwd is None else (project_root / cwd)
    target = target.resolve()
    if not target.is_dir():
        raise RunnerError(f"cwd does not exist: {target}")
    return target


def _build_bash_script(
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
) -> str:
    lines = [
        "set -e",
        f"cd {shlex.quote(str(cwd))}",
    ]
    for cmd in commands:
        lines.append(f"printf '\\033[2m$ %s\\033[0m\\n' {shlex.quote(cmd)}")
        lines.append(cmd)
    lines.append(f"env -0 > {shlex.quote(str(raw_env_path))}")
    return "\n".join(lines) + "\n"


def _parse_env_nul(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for chunk in data.split(b"\x00"):
        if not chunk:
            continue
        try:
            key, _, value = chunk.decode("utf-8", "replace").partition("=")
        except Exception:
            continue
        if key:
            result[key] = value
    return result


def _format_for_shell(
    shell: str,
    added: dict[str, str],
    removed: set[str],
) -> str:
    if shell == "fish":
        return format_fish(added, removed)
    # bash and zsh share the same output.
    return format_bash(added, removed)
