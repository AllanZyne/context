# ctx

Run hierarchical commands defined in a project's `context.yaml`, with
environment-variable changes automatically propagated back to your
shell (bash/zsh/fish).

## Install

Install the binary via `uv`:

```bash
uv tool install git+https://github.com/AllanZyne/context
# or, from a local checkout:
uv tool install .
```

Then add **one** line to your shell rc, picking the method you prefer:

### Method A — dynamic (works with install-only)

```bash
# ~/.bashrc
eval "$(ctx-bin shellinit bash)"

# ~/.zshrc
eval "$(ctx-bin shellinit zsh)"

# ~/.config/fish/config.fish
ctx-bin shellinit fish | source
```

The binary generates the wrapper on every shell startup.

### Method B — static (requires repo checkout)

If you have the repo cloned, you can source a static file directly
instead — slightly faster shell startup, and you can read/edit the
wrapper easily:

```bash
# ~/.bashrc
source /path/to/ctx/shells/ctx.bash

# ~/.zshrc
source /path/to/ctx/shells/ctx.zsh

# ~/.config/fish/config.fish
source /path/to/ctx/shells/ctx.fish
```

The static files under `shells/` are byte-identical to the
`shellinit` output — a test enforces this, so they won't drift.

## Upgrade

```bash
uv tool upgrade ctx
# or from a local checkout:
uv tool install --reinstall .
```

After upgrading, restart your shell (or re-source your rc) so the
wrapper is refreshed.

- **Method A users**: the wrapper is regenerated on every shell
  startup, so a new shell picks up any changes automatically.
- **Method B users**: `git pull` your checkout, then
  `source shells/ctx.<shell>` again (or restart your shell). The
  wrapper itself rarely changes — most upgrades are binary-only and
  require no re-sourcing.

## Usage

Create a `context.yaml` at your project root:

```yaml
commands:
  init:
    desc: Install deps
    run:
      - uv sync
  build:
    prod:
      cwd: ./app
      env:
        NODE_ENV: production
      run:
        - docker build -t app:prod .
    dev:
      run:
        - docker build -t app:dev .
  activate:
    run:
      - source .venv/bin/activate   # VIRTUAL_ENV propagates back
```

Then, from any directory under the project:

```
$ ctx init                # runs commands.init.run
$ ctx build prod          # runs commands.build.prod.run
$ ctx activate            # env changes flow back to your shell
$ echo $VIRTUAL_ENV       # now set
```

## `context.yaml` reference

The top-level must have a single key, `commands`, whose value is a
mapping. Each entry is either a **group** (whose values are more
entries, forming a subcommand tree) or a **leaf** (a concrete
command, identified by the presence of a `run` key).

### Leaf fields

| Field  | Type             | Required | Description                                                                                                                                   |
|--------|------------------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `run`  | list of strings  | yes      | Shell commands executed in order under a single `bash -c` invocation with `set -e`. Pipes, redirections, `source`, and `cd` all work as you'd expect; state (cwd, vars) carries between entries. Empty strings are rejected. |
| `desc` | string           | no       | Human description, reserved for future `--help`-style listing. Accepted but currently unused at runtime.                                      |
| `cwd`  | string           | no       | Working directory for the command, **relative to the directory containing `context.yaml`**. Must exist at execution time. Defaults to the yaml's own directory. |
| `env`  | mapping          | no       | Extra environment variables layered on top of the inherited shell env. Scalars (`string`/`int`/`bool`) are coerced to strings; lists/dicts are rejected. |

### Group rules

A group node is just any node **without** a `run` key. Each of its keys
names a subcommand. Nesting is unlimited:

```yaml
commands:
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
integration). If you define `commands.shellinit`, it is shadowed — the
built-in wins. Any other name is fair game.

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
