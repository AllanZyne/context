# `ctx` — Hierarchical command runner with env writeback

**Status:** Draft
**Date:** 2026-05-07

## 1. Goal

A Python CLI tool called `ctx` that:

1. Walks up from the current directory to find a `context.yaml` file.
2. Reads a tree of commands from that file, keyed by the CLI arguments
   (`ctx build prod` → `commands.build.prod.run`).
3. Runs those commands, streaming output to the terminal.
4. Propagates any environment variable changes made by those commands
   **back to the user's parent shell** (bash, zsh, or fish).

Managed with `uv`. No support for argument pass-through to commands —
the YAML fully determines what runs.

## 2. User experience

### 2.1 Installing

```bash
uv tool install ctx          # installs the ctx-bin executable
```

Then the user adds one line to their shell rc:

```bash
# ~/.bashrc or ~/.zshrc
eval "$(ctx-bin shellinit bash)"   # or zsh

# ~/.config/fish/config.fish
ctx-bin shellinit fish | source
```

This defines a shell function called `ctx` that wraps `ctx-bin` and
sources the env writeback file after a successful run.

### 2.2 Writing `context.yaml`

```yaml
commands:
  init:
    desc: Install dependencies
    run:
      - uv sync
      - pre-commit install

  build:
    prod:
      desc: Production build
      cwd: ./app
      env:
        NODE_ENV: production
      run:
        - docker build -t app:prod .
        - docker push app:prod
    dev:
      run:
        - docker build -t app:dev .

  activate:
    run:
      - source .venv/bin/activate   # VIRTUAL_ENV/PATH will propagate back
```

### 2.3 Running

```
$ ctx init                # runs commands.init.run
$ ctx build prod          # runs commands.build.prod.run
$ ctx activate            # runs source, env lands in the parent shell
$ echo $VIRTUAL_ENV       # set — the shell inherited the change
```

## 3. Architecture

### 3.1 Package layout

```
context/
├── pyproject.toml
├── README.md
├── src/
│   └── ctx/
│       ├── __init__.py
│       ├── __main__.py        # python -m ctx
│       ├── cli.py             # entry point, argv dispatch
│       ├── config.py          # find + load + validate context.yaml
│       ├── resolver.py        # tokens → leaf node (pure function)
│       ├── runner.py          # execute leaf, produce env diff
│       ├── shellinit.py       # emit shell wrapper source
│       └── emit.py            # env diff → shell source (bash/zsh/fish)
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_resolver.py
    ├── test_runner.py
    ├── test_shellinit.py
    └── test_integration.py    # real shell subprocess
```

### 3.2 Module boundaries

| Module | Input | Output | Depends on |
|---|---|---|---|
| `config` | starting dir | `(data: dict, yaml_path: Path)` | PyYAML, filesystem |
| `resolver` | `data`, argv tokens | `LeafNode` or typed error | pure function |
| `runner` | `LeafNode`, project root, target shell | `exit_code: int` (side effect: writes to `$CTX_ENV_DUMP` if set and success) | subprocess, bash, filesystem |
| `emit` | original env, new env, target shell | shell source string | pure function |
| `shellinit` | target shell name | wrapper source string | pure function |
| `cli` | `sys.argv`, `os.environ` | exit code | all of the above |

Rationale for making `resolver` and `emit` pure functions: the trickiest
logic lives there (path matching, leaf/group disambiguation, shell
quoting per dialect). Pure functions are exhaustively testable with
in-memory fixtures, no tmp dirs or mocks.

### 3.3 Request flow

```
user $ ctx build prod
    │
    ▼
shell function `ctx` (from shellinit)
    │   sets CTX_ENV_DUMP=<tmpfile>
    │   invokes: command ctx-bin build prod
    ▼
cli.main():
    1. config.find_and_load(cwd) → data, yaml_path
    2. resolver.resolve(data, ["build","prod"]) → LeafNode
    3. runner.run_leaf(leaf, yaml_path.parent, shell=<from --shell flag>)
       • snapshots os.environ
       • builds a bash script: set -e; cd ...; echo "$ cmd"; cmd; ...; env -0 > dump
       • subprocess.run(["bash","-c",script], env=merged, cwd=cwd)
       • on exit 0: diff envs, emit.format(diff, shell) → writes CTX_ENV_DUMP
       • on failure: leaves CTX_ENV_DUMP empty → wrapper won't source anything
    4. return exit code
    │
    ▼
shell function sources CTX_ENV_DUMP if non-empty, deletes it, returns rc
```

## 4. YAML schema

### 4.1 Grammar

```
root         := { "commands": <group> }
group        := dict<name, node>                  # at least one entry
node         := <group_node> | <leaf_node>
group_node   := dict<name, node>                  # no leaf keys
leaf_node    := {
                  "run": list<string>,            # required, non-empty
                  "desc"?: string,
                  "cwd"?: string,                 # relative to yaml dir
                  "env"?: dict<string, string>
                }
```

Reserved leaf keys: `run`, `desc`, `cwd`, `env`. Any other key at a node
level makes it a group node; its children must be nodes recursively.

### 4.2 Validation (enforced at load time)

1. File exists and parses as YAML.
2. Top-level has a `commands` key mapping to a dict.
3. For every node:
   - If it has `run`, it is a leaf. Allowed sibling keys are the reserved
     set. Any other sibling key → error: *"leaf node `<path>` has
     unexpected key `<key>`; a node with `run` cannot also have
     sub-commands"*.
   - If it does not have `run`, every key is a sub-command name and its
     value must be a dict (recurse).
   - A node with neither `run` nor sub-commands → error: *"empty node
     `<path>`"*.
4. `run` must be a non-empty list of non-empty strings.
5. `env`, if present, must be a dict. Keys must be strings. Values are
   coerced to strings via `str(value)` so `FOO: 1` and `FOO: true` both
   work and become `"1"` / `"True"`. Lists and dicts as values → error.
6. `cwd`, if present, must be a string. Resolution to a filesystem path
   is deferred to runner; a non-existent directory is caught at execution
   time.

Error messages always include the dotted path to the offending node.

## 5. Command resolution (`resolver.py`)

Pure function `resolve(data, tokens) -> LeafNode | ResolveError`.

**Built-in subcommand reservation**: `cli.py` intercepts
`ctx-bin shellinit <shell>` **before** touching the YAML or calling the
resolver. If a user defines `commands.shellinit` in their YAML it is
shadowed by the builtin — documented as a reserved name. No other
builtins exist in v0.1.

- Start at `data["commands"]`.
- Pop tokens one at a time, descend.
- At each step:
  - If the current node is a leaf (`run` in keys) and tokens are left →
    error: *"command `<matched>` takes no further arguments"* (recall: no
    argument pass-through).
  - If the current node is a group and the next token is not a key →
    error: *"unknown subcommand `<token>` under `<path>`"* with a list of
    valid next tokens.
- When tokens are exhausted:
  - If current node is a leaf → return it.
  - If current node is a group → error with list of valid subcommands
    (exit code 2, printed to stderr).
- With zero tokens (`ctx` with no args) → print top-level subcommand
  listing and exit 0.

## 6. Execution (`runner.py`)

### 6.1 Signature

```python
@dataclass
class LeafNode:
    path: tuple[str, ...]      # for error messages
    run: list[str]
    cwd: str | None
    env: dict[str, str]

def run_leaf(leaf: LeafNode, project_root: Path, shell: str) -> int:
    """
    Executes the leaf's commands in a single bash subprocess.
    On success, writes env writeback source to $CTX_ENV_DUMP.
    Returns subprocess exit code.
    """
```

### 6.2 Execution algorithm

1. **Resolve cwd**: `project_root / leaf.cwd` if `leaf.cwd` else
   `project_root`. Must exist and be a directory; otherwise error and
   exit 1 before launching subprocess.
2. **Build env**: start from `os.environ.copy()`, update with
   `leaf.env`. This is passed to subprocess.
3. **Snapshot**: remember this merged env as `initial_env` for diff.
4. **Construct bash script**:

   ```bash
   set -e
   cd <shlex.quote(cwd)>
   printf '\033[2m$ %s\033[0m\n' <shlex.quote(cmd1)>
   <cmd1>
   printf '\033[2m$ %s\033[0m\n' <shlex.quote(cmd2)>
   <cmd2>
   ...
   env -0 > "$_CTX_RAW_ENV"
   ```

   `_CTX_RAW_ENV` is a tmpfile allocated by Python (not the same file
   as `$CTX_ENV_DUMP`). The user's commands are untouched, as they
   appeared in the YAML — they run through bash so pipes, redirections,
   `source`, etc. work.
5. **Execute**:
   ```python
   subprocess.run(["bash", "-c", script], env=initial_env, cwd=cwd)
   ```
   stdout/stderr inherit from the parent (ctx-bin), which inherits from
   the user's terminal. No buffering, no capturing.
6. **On success (exit 0)**:
   - Read `_CTX_RAW_ENV`, parse as NUL-separated `KEY=VALUE` pairs into
     `final_env`.
   - Diff `initial_env` vs `final_env` → `(added, changed, removed)`.
   - If the user set `$CTX_ENV_DUMP` (wrapper is installed), call
     `emit.format(diff, shell)` and write the result to
     `$CTX_ENV_DUMP`.
7. **On failure**:
   - Do **not** write to `$CTX_ENV_DUMP` (it remains empty).
   - Wrapper will see empty file, skip sourcing — no env changes leak.
8. **Cleanup**: delete `_CTX_RAW_ENV`.

### 6.3 Why always use bash

Commands are always executed with `/bin/bash`, regardless of the user's
login shell. This is intentional:

- YAML authors get a predictable command dialect (pipes, `$VAR`, `[[ ]]`,
  `source`, `&&`, etc.) — not the union of bash/zsh/fish quirks.
- `set -e`, `env -0`, `printf` behave consistently.
- fish users who authored the YAML can still use bash syntax in `run:`
  without confusion.

Shell awareness is **only** for env writeback syntax in `emit.py`, not
command execution.

### 6.4 Command echo

Before each command, print a dim-colored `$ <cmd>` line via `printf` so
users see what's running. This is done inside the bash script (not
Python) so it interleaves correctly with command output.

## 7. Env writeback (`emit.py`)

### 7.1 Diff

```python
def diff_env(before: dict, after: dict) -> tuple[
    dict[str, str],   # added + changed (key → new value)
    set[str],         # removed keys
]
```

Edge case: variables that existed before and still exist with the same
value are omitted.

Shell-internal variables that should **not** be written back (they are
per-shell-instance and would corrupt the parent):

- Skip if key starts with `_CTX_` (our own internal scratchpad).
- Skip keys exported by bash but meaningless elsewhere: `PWD`, `OLDPWD`,
  `SHLVL`, `_` (underscore), `PPID`. (These change naturally in any
  subprocess and re-exporting them to the parent shell would be wrong.)

### 7.2 Shell-specific emission

**bash / zsh** (`emit.format(diff, "bash")` — same output for zsh):

```bash
export FOO=$'bar'
export PATH=$'/new/path:/usr/bin'
unset OLD_VAR
```

Values are emitted using bash `$'...'` ANSI-C quoting. This handles
newlines, tabs, NULs, and any byte safely. A value `abc\n"def'` becomes
`$'abc\n"def\''`. Python implementation: escape backslashes, single
quotes, control bytes to `\xNN`, newlines to `\n`, tabs to `\t`.

**fish** (`emit.format(diff, "fish")`):

```fish
set -gx FOO 'bar'
set -gx PATH '/new/path:/usr/bin'
set -e OLD_VAR
```

fish uses `set -gx` for global-exported. Single-quoted strings in fish
accept almost anything except `'` and `\`, which are escaped. Values
with newlines are split across lines using fish's string continuation
rules. Implementation falls back to building the string via
concatenation of safe segments and `\x` escapes if needed.

### 7.3 Shell detection

The wrapper passes `--shell={bash,zsh,fish}` explicitly (the wrapper
*knows* what shell it lives in). `ctx-bin` doesn't have to guess from
`$SHELL`.

## 8. Shell wrappers (`shellinit.py`)

### 8.1 bash / zsh wrapper

Emitted by `ctx-bin shellinit bash` (identical output for zsh):

```bash
ctx() {
  local _ctx_dump
  _ctx_dump=$(mktemp -t ctx-env.XXXXXX) || return 1
  CTX_ENV_DUMP="$_ctx_dump" command ctx-bin --shell=bash "$@"
  local _ctx_rc=$?
  if [ $_ctx_rc -eq 0 ] && [ -s "$_ctx_dump" ]; then
    . "$_ctx_dump"
  fi
  rm -f "$_ctx_dump"
  return $_ctx_rc
}
```

For zsh, only the `--shell=zsh` arg differs (content is identical).

### 8.2 fish wrapper

```fish
function ctx
    set -l _ctx_dump (mktemp -t ctx-env.XXXXXX)
    or return 1
    CTX_ENV_DUMP=$_ctx_dump command ctx-bin --shell=fish $argv
    set -l _ctx_rc $status
    if test $_ctx_rc -eq 0 -a -s $_ctx_dump
        source $_ctx_dump
    end
    rm -f $_ctx_dump
    return $_ctx_rc
end
```

### 8.3 Design notes

- The binary is called `ctx-bin`, not `ctx`, to avoid recursion when the
  user's shell expands `ctx` to the function. `command ctx-bin` bypasses
  function lookup.
- If a user skips the `eval "$(ctx-bin shellinit …)"` step, they'll
  still be able to invoke `ctx-bin build prod` directly — commands run,
  but env writeback is silently dropped (wrapper is what sets
  `CTX_ENV_DUMP`). This degrades gracefully.

## 9. Error handling

| Scenario | Behavior |
|---|---|
| No `context.yaml` up to filesystem root | stderr: *"no context.yaml found (searched from …)"*, exit 1. **Exception**: the `shellinit` subcommand does not require a `context.yaml` — it only emits wrapper source. |
| YAML parse error | stderr: line/col from PyYAML, exit 1 |
| Schema validation error | stderr: node path + human message, exit 1 |
| Unknown subcommand | stderr: *"unknown subcommand `foo` under `build`. Valid: prod, dev"*, exit 2 |
| Leaf takes no more args | stderr: *"command `build prod` takes no further arguments (got `extra`)"*, exit 2 |
| `cwd` directory missing | stderr: *"cwd does not exist: …"*, exit 1 |
| Command failure (non-zero exit) | bash's `set -e` exits at first failure; we inherit exit code. No env writeback. |
| Interrupted (Ctrl-C) | SIGINT to bash child, bubble up; no env writeback. |

## 10. Testing strategy

### 10.1 Unit tests (pure logic)

- **`test_config.py`**: parametrised YAML fixtures × expected errors.
  Covers every validation rule.
- **`test_resolver.py`**: in-memory dicts. Covers:
  - Correct leaf returned for multi-level paths
  - Group-with-leftover-tokens errors
  - Leaf-with-leftover-tokens errors
  - Empty argv case
- **`test_emit.py`**: diff calculation, bash quoting edge cases (newlines,
  single quotes, NULs, non-ASCII), fish quoting edge cases, filtered
  keys (`PWD`, `OLDPWD`, etc.).
- **`test_shellinit.py`**: output contains `ctx()` (bash/zsh) or
  `function ctx` (fish); no placeholder leakage.

### 10.2 Execution tests (real subprocess)

- **`test_runner.py`**:
  - `run: [echo hi]` → stdout contains "hi", exit 0, empty diff.
  - `run: [export FOO=bar]` → diff contains `FOO=bar`.
  - `run: [false]` → non-zero exit, no writeback file populated.
  - `cwd` respected.
  - `env` meta field visible to commands.

### 10.3 Integration tests (real shell)

`test_integration.py` uses real `bash` (and `fish` if available) via
subprocess:

```python
script = f"""
    eval "$(ctx-bin shellinit bash)"
    cd /tmp/fixture_project
    ctx activate
    echo "FOO=$FOO"
"""
out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
assert "FOO=bar" in out.stdout
```

This is the only way to catch wrapper-syntax bugs (quoting in the eval'd
wrapper source, fd handling, etc.).

## 11. `pyproject.toml`

```toml
[project]
name = "ctx"
version = "0.1.0"
description = "Hierarchical command runner with shell env writeback"
requires-python = ">=3.10"
dependencies = ["PyYAML>=6.0"]

[project.scripts]
ctx-bin = "ctx.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/ctx"]
```

Install flow during development:

```bash
uv sync --group dev              # create .venv, install deps + dev deps
uv run pytest                    # run tests
uv run ctx-bin shellinit bash    # try the wrapper
uv tool install .                # install into user's tool env
```

## 12. Out of scope (YAGNI)

These are explicitly not in v0.1:

- Argument pass-through to commands (`ctx test -- -k login`). Commands
  are exactly what's in YAML.
- Variable interpolation / templating in YAML values.
- Conditional commands (`run_if`, `when`).
- Dependencies between commands (`needs: [other-cmd]`).
- `--verbose`/`--quiet` flags. Output strategy is fixed.
- Shells other than bash, zsh, fish.
- Windows support.
- Global config / profiles.
- Color/theming controls.
