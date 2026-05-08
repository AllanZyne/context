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
