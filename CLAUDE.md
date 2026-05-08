# CLAUDE.md — notes for future sessions on this repo

Keep this file short. Record only things that (a) are easy to get wrong
and (b) aren't obvious from just reading the code or the README.

## Working agreement with the user (do NOT deviate)

1. **Don't create `docs/superpowers/specs/` or `docs/superpowers/plans/`
   files** unless the user explicitly asks. When a superpowers skill
   (brainstorming, writing-plans) wants to save a design or plan
   document, skip the file write and keep it in chat.
2. **Don't run `git commit`** (or `git add` + commit) unless the user
   explicitly asks. Leave changes in the working tree after editing so
   the user can review. Read-only git (`status`, `diff`, `log`) is
   fine.

## What this is

A Python CLI (`ctx-bin`, wrapped as a shell function `ctx`) that reads a
hierarchical `context.yaml`, runs commands under `/bin/bash`, and
propagates env-var changes back to the parent shell (bash/zsh/fish).
User-facing docs live in `README.md`; the design spec is at
`docs/superpowers/specs/2026-05-07-ctx-design.md`.

## Commands

```bash
uv sync --group dev                     # create .venv + install deps
uv run pytest                           # full suite (~2s)
uv run pytest tests/test_integration.py # real shell subprocess tests
uv tool install --reinstall .           # install ctx-bin into uv tool env
```

Integration tests spawn real `bash` / `zsh` / `fish` and invoke ctx-bin
via `uv --directory {REPO_ROOT} run ctx-bin` — they do **not** rely on
`uv tool install` having run. zsh and fish tests auto-skip if missing.

## Layout

```
src/ctx/
  cli.py         argv dispatch + --shell= flag + shellinit reservation
  config.py      find_yaml() walks up; load_and_validate() schema checks
  resolver.py    pure fn: tokens → LeafNode | GroupListing
  runner.py      single bash -c subprocess; env -0 diff; writes CTX_ENV_DUMP
  emit.py        pure fns: diff_env, format_bash, format_fish
  shellinit.py   wrapper templates emitted by `ctx-bin shellinit <shell>`

shells/ctx.{bash,zsh,fish}    static copies of shellinit() output
docs/superpowers/{specs,plans}/   design + implementation docs
tests/test_*.py                pytest, one per module + test_integration.py
```

## Invariants that will break silently if violated

1. **`shells/ctx.{bash,zsh,fish}` must byte-match `shellinit(<shell>)` output.**
   Enforced by `test_static_wrapper_matches_shellinit` (in
   `tests/test_integration.py`). If you edit `shellinit.py`'s templates,
   update the static files too — the drift test compares after stripping
   the leading comment header only.

2. **The wrapper must not create any file until ctx-bin writes to it.**
   Uses `mktemp -u` (name only, no file). Combined with: runner.py only
   writes `CTX_ENV_DUMP` when the env diff is non-empty. Combined with:
   wrapper cleanup is guarded by `[ -e ]` / `test -e`. Rationale: a
   stray `removed '...'` trailer was visible to users who had
   `alias rm='rm -v'`. See regression tests
   `test_bash_wrapper_no_tmpfile_when_yaml_missing` and
   `test_bash_wrapper_ignores_rm_alias`.

3. **Wrapper cleanup must use `command rm`**, not bare `rm`. Users often
   alias or function-shadow `rm`; `command` bypasses both.

4. **Commands always execute under `/bin/bash`**, regardless of the
   user's interactive shell. The `--shell=` flag only changes which
   writeback syntax Python emits (bash/zsh/fish `export` / `set -gx`).
   Don't "simplify" this to use the parent shell for execution — it
   would force users to write fish-syntax commands in YAML.

5. **`resolver.py` and `emit.py` are pure functions** — no filesystem,
   no subprocess. This is intentional so their tests use in-memory
   dicts. Keep it that way.

6. **Reserved subcommand: `shellinit`**. Intercepted in `cli.py` before
   YAML loading. User-defined `commands.shellinit` is shadowed. Adding
   more reserved names? Document them in README §"Reserved names".

7. **Env keys never written back to parent shell**: `PWD`, `OLDPWD`,
   `SHLVL`, `_`, `PPID`, anything starting with `_CTX_`. Defined in
   `FILTERED_KEYS` in `emit.py`. Adding to this list is usually safe;
   removing is not.

## YAML schema quirks

- Top-level is **directly** the command mapping — no wrapper key.
  (`init: {run: [...]}`, not `commands: {init: {...}}`.)
- `env` values: scalars (str/int/bool) are coerced to strings via
  `str()` before use; lists/dicts are rejected at load time.
- Leaf/group disambiguation: presence of `run` key → leaf. A node
  with `run` plus any non-reserved sibling (anything outside
  `{run, desc, cwd, env}`) is rejected.

## Git / workflow gotchas

- The repo has had several branch flips (feature/ctx → squash-merge →
  main → fix/… etc.). If `docs/superpowers/specs/` looks "missing" in
  `git status`, it's almost certainly because commits for it landed on
  another branch. Run `git log <branch> -- docs/superpowers/` before
  panicking — the files are usually in history, just not checked out
  on the current branch. Restore with `git checkout <ref> -- docs/`.
- `uv.lock` should be committed. It was missed in the scaffold commit
  and added later.

## Common implementation tasks

- **Changing wrapper behavior**: edit `shellinit.py` templates AND
  `shells/*` in the same commit, or the drift test fails.
- **Changing the YAML schema**: update `config.py` validation, every
  test fixture (there are many in `test_config.py`, `test_cli.py`,
  `test_integration.py`), the spec, AND the README's reference table.
- **Adding a test that runs a real shell**: follow the
  `_has("bash") / skipif` pattern already in `test_integration.py`.
  Pass `env={**os.environ}` so PATH reaches the subprocess.

## Writing style

- No emojis in code or docs unless the user asks.
- README is user-facing and should stay opinionated ("do this"); this
  file is for implementer-facing quirks and invariants.
