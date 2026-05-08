SUPPORTED_SHELLS: tuple[str, ...] = ("bash", "zsh", "fish")


_BASH_TEMPLATE = """\
ctx() {{
  local _ctx_dump _ctx_src
  _ctx_dump=$(mktemp -u -t ctx-env.XXXXXX) || return 1
  _ctx_src=$(mktemp -u -t ctx-src.XXXXXX) || return 1
  CTX_ENV_DUMP="$_ctx_dump" CTX_SOURCE_SCRIPT="$_ctx_src" \\
    command ctx-bin --shell={shell} "$@"
  local _ctx_rc=$?
  if [ $_ctx_rc -eq 0 ]; then
    if [ -s "$_ctx_src" ]; then
      . "$_ctx_src"
      _ctx_rc=$?
    elif [ -s "$_ctx_dump" ]; then
      . "$_ctx_dump"
    fi
  fi
  [ -e "$_ctx_dump" ] && command rm -f "$_ctx_dump"
  [ -e "$_ctx_src" ] && command rm -f "$_ctx_src"
  return $_ctx_rc
}}
"""

_FISH_TEMPLATE = """\
function ctx
    set -l _ctx_dump (mktemp -u -t ctx-env.XXXXXX)
    or return 1
    set -l _ctx_src (mktemp -u -t ctx-src.XXXXXX)
    or return 1
    CTX_ENV_DUMP=$_ctx_dump CTX_SOURCE_SCRIPT=$_ctx_src \\
        command ctx-bin --shell=fish $argv
    set -l _ctx_rc $status
    if test $_ctx_rc -eq 0
        if test -s $_ctx_src
            source $_ctx_src
            set _ctx_rc $status
        else if test -s $_ctx_dump
            source $_ctx_dump
        end
    end
    if test -e $_ctx_dump
        command rm -f $_ctx_dump
    end
    if test -e $_ctx_src
        command rm -f $_ctx_src
    end
    return $_ctx_rc
end
"""


def shellinit(shell: str) -> str:
    """Return the wrapper source to be eval'd (bash/zsh) or sourced (fish)."""
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(
            f"unsupported shell {shell!r}; expected one of {SUPPORTED_SHELLS}"
        )
    if shell == "fish":
        return _FISH_TEMPLATE
    return _BASH_TEMPLATE.format(shell=shell)
