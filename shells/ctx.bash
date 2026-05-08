# ctx shell integration for bash.
#
# This file is a static copy of what `ctx-bin shellinit bash` emits.
# Both installation methods are supported:
#
#   A) Installed binary only (no repo access):
#        eval "$(ctx-bin shellinit bash)"      # add to ~/.bashrc
#
#   B) Source this file directly (if you have the repo checked out):
#        source /path/to/ctx/shells/ctx.bash   # add to ~/.bashrc
#
# A drift-prevention test ensures this file stays byte-identical to the
# shellinit() output.

ctx() {
  local _ctx_dump _ctx_src
  _ctx_dump=$(mktemp -u -t ctx-env.XXXXXX) || return 1
  _ctx_src=$(mktemp -u -t ctx-src.XXXXXX) || return 1
  CTX_ENV_DUMP="$_ctx_dump" CTX_SOURCE_SCRIPT="$_ctx_src" \
    command ctx-bin --shell=bash "$@"
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
}
