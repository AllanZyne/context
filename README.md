# ctx

Run hierarchical commands defined in a project's `context.yaml`, with
environment-variable changes automatically propagated back to your
shell (bash/zsh/fish).

## Install

### Option 1 — from GitHub

```bash
uv tool install git+https://github.com/AllanZyne/context
```

### Option 2 — from a local checkout

```bash
# 1. Clone the repo wherever you keep source code.
git clone https://github.com/AllanZyne/context.git
cd context

# 2. Install the ctx-bin executable into uv's tool environment.
#    --reinstall is safe to re-run on every `git pull`.
uv tool install --reinstall .

# 3. Verify the binary is on your PATH.
which ctx-bin            # should print something under ~/.local/share/uv/tools
ctx-bin shellinit bash   # should print a bash `ctx() { ... }` function
```

### Shell integration

After the install step above, add **one** line to your shell rc:

```bash
# ~/.bashrc
eval "$(ctx-bin shellinit bash)"

# ~/.zshrc
eval "$(ctx-bin shellinit zsh)"

# ~/.config/fish/config.fish
ctx-bin shellinit fish | source
```

Open a new shell (or re-source your rc) and `ctx` will be available as
a shell function that forwards to `ctx-bin` and applies any env
changes back to your shell.

## Upgrade

```bash
uv tool upgrade ctx
# or, for a local checkout:
cd /path/to/ctx && git pull && uv tool install --reinstall .
```

The wrapper is regenerated on every shell startup, so a new shell
picks up any changes automatically. No need to re-edit your rc.

## Usage

Create a `context.yaml` at your project root:

```yaml
init:
  desc: Install deps
  run:
    - uv sync
build:
  prod:
    cwd: ./app
    env:
      NODE_ENV: production          # visible during the build only
    run:
      - docker build -t app:prod .
  dev:
    run:
      - docker build -t app:dev .
test:
  run:
    - pytest {args}                 # `ctx test -k login` → pytest -k login
use-python-3.12:
  export:
    PYTHON_VERSION: "3.12"          # lives on in your shell after the command
  run:
    - pyenv local 3.12.0
activate:
  run:
    - source .venv/bin/activate     # VIRTUAL_ENV propagates back
```

Then, from any directory under the project:

```
$ ctx init                # runs init.run
$ ctx build prod          # runs build.prod.run
$ ctx test -k login       # runs pytest -k login (via {args})
$ ctx use-python-3.12     # sets PYTHON_VERSION in your shell (via export:)
$ ctx activate            # env changes from `source` flow back
$ echo $VIRTUAL_ENV       # now set
```

## `context.yaml` reference

The top-level is a mapping of subcommand names. Each entry is either a
**group** (whose values are more entries, forming a subcommand tree)
or a **leaf** (a concrete command, identified by the presence of a
`run` key).

### Leaf fields

| Field    | Type             | Required | Description                                                                                                                                   |
|----------|------------------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `run`    | list of strings  | yes      | Shell commands executed in order under a single `bash -c` invocation with `set -e`. Pipes, redirections, `source`, and `cd` all work as you'd expect; state (cwd, vars) carries between entries. Empty strings are rejected. |
| `desc`   | string           | no       | Human description, reserved for future `--help`-style listing. Accepted but currently unused at runtime.                                      |
| `cwd`    | string           | no       | Working directory for the command, **relative to the directory containing `context.yaml`**. Must exist at execution time. Defaults to the yaml's own directory. |
| `env`    | mapping          | no       | Extra environment variables for the command. **Local to this run** — values are visible to the command but **do not** propagate back to the parent shell unless the command itself mutates them. Scalars (`string`/`int`/`bool`) are coerced to strings; lists/dicts are rejected. |
| `export` | mapping          | no       | Same shape as `env`, but values **always** flow back to the parent shell after a successful run. Use this when you want the command's purpose to be "set some variables." A key may appear in `env` **or** `export`, not both. |

### Argument forwarding via `{args}`

Any `{args}` placeholder in a `run:` string is replaced at execution
time with whatever tokens the user passed after the subcommand path,
shell-quoted for safety:

```yaml
test:
  run:
    - pytest {args}

fmt:
  run:
    - ruff format {args|.}   # default: format the current dir
```

```
$ ctx test                    # → pytest
$ ctx test -k login -x        # → pytest -k login -x
$ ctx test "name with spaces" # → pytest 'name with spaces'
$ ctx fmt                     # → ruff format .   (default kicks in)
$ ctx fmt src/foo.py          # → ruff format src/foo.py
```

Syntax:

- `{args}` — substituted with the captured tokens (empty string if none).
- `{args|anything up to the closing brace}` — if the user passes no
  extra tokens, the default after `|` is inserted **verbatim** (not
  re-quoted); the YAML author controls its shape directly.

If no `run:` string contains `{args}` (or `{args|...}`), passing extra
tokens still errors with *"command X takes no further arguments"* —
behavior is unchanged for subcommands that don't opt in.

### Group rules

A group node is just any node **without** a `run` key. Each of its keys
names a subcommand. Nesting is unlimited:

```yaml
deploy:
  staging:
    k8s:
      run:
        - kubectl apply -f k8s/staging
```

invoked as `ctx deploy staging k8s`.

A node **cannot** be both a leaf and a group. If you put `run:` on a
node that already has non-reserved sibling keys, validation fails at
load time with the full path of the offending node.

### Reserved names

`shellinit` is reserved as a built-in subcommand (used during shell
integration). If you define a top-level `shellinit`, it is shadowed —
the built-in wins. Any other name is fair game.

### Behavior notes

- Commands execute under `/bin/bash` with `set -e` — pipes, `source`,
  `cd`, and bash variable expansion work regardless of your
  interactive shell.
- All commands in a single `run:` share one shell process, so
  `cd some/dir` in command 1 affects command 2, and env assignments
  persist across the list.
- **Env writeback only happens on full success.** A single failed
  command aborts `set -e` and no env changes are propagated.
- The following shell-internal variables are **never** written back
  to the parent shell (they would corrupt it): `PWD`, `OLDPWD`,
  `SHLVL`, `_`, `PPID`, and anything starting with `_CTX_`.

### Exit codes

| Code | Meaning                                                                      |
|------|------------------------------------------------------------------------------|
| 0    | Command ran successfully (or tokens resolved to a group listing).            |
| 1    | Setup error: missing `context.yaml`, schema error, missing `cwd`, or invalid `--shell=`. |
| 2    | Resolution error: unknown subcommand, or extra tokens after a leaf.          |
| n    | Any other non-zero value is propagated directly from the failing command.    |

## Development

```bash
uv sync --group dev
uv run pytest
```
