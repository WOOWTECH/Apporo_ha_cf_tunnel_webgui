#!/usr/bin/env bash
# Execute the real runtime entry point with a stub cloudflared. No root or
# Cloudflare credentials are required. This is a public-process seam test.
#
# Usage:  bash cloudflared/tests/test_token_safety.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"

# `set -e` ignores a command negated with `!`, so every assertion fails the
# test explicitly instead. Fixed-string matches only (grep -F).
fail() { echo "FAIL: $*" >&2; exit 1; }
has() { grep -qF -- "$1" "${@:2}" || fail "expected '$1' in ${*:2}"; }
lacks() {
    if grep -qF -- "$1" "${@:2}" 2>/dev/null; then fail "found '$1' in ${*:2}"; fi
}

cat > "$work/bin/cloudflared" <<'STUB'
#!/bin/sh
printf '%s\n' "$@" > "$ARGV_RECORD"
STUB
chmod +x "$work/bin/cloudflared"

cat > "$work/bashio.sh" <<'STUB'
bashio::log.info() { echo "[INFO] $*"; }
bashio::log.debug() { echo "[DEBUG] $*"; }
bashio::log.notice() { echo "[NOTICE] $*"; }
bashio::log.warning() { echo "[WARNING] $*"; }
bashio::log.error() { echo "[ERROR] $*"; }
bashio::log.trace() { echo "[TRACE] $*"; }
bashio::log.log() { echo "[$1] $2"; }
bashio::config.true() { return 1; }
# Credential permissions have their own test (test_credential_permissions.py).
cloudflared-credential-guard() { return 0; }
bashio::config.has_value() {
    [[ "${SIMULATE_UNCONFIGURED:-0}" != 1 ]] &&
        [[ "$1" == tunnel_token || ( "$1" == run_parameters && -n "${RUN_PARAMS:-}" ) ]]
}
bashio::config() {
    if [[ "$1" == run_parameters ]]; then printf '%s' "$RUN_PARAMS";
    else printf '%s' 'TEST_SECRET_DO_NOT_LOG'; fi
}
STUB

# Runs rootfs/run.sh; stdout and stderr both land in $work/log.
run_entry() {
    PATH="$work/bin:$PATH" bash -c 'source "$1"; source "$2"' _ \
        "$work/bashio.sh" "$root/cloudflared/rootfs/run.sh" > "$work/log" 2>&1
}

export ARGV_RECORD="$work/argv"
export CLOUDFLARED_TOKEN_FILE="$work/token"

# Token mode: the token reaches cloudflared only as a private file.
run_entry || fail "token mode did not start cloudflared"
has '--token-file=' "$work/argv"
lacks '--token=' "$work/argv"
has '--metrics=127.0.0.1:36500' "$work/argv"
test "$(cat "$work/token")" = 'TEST_SECRET_DO_NOT_LOG' || fail "token file holds the wrong value"
test "$(stat -c %a "$work/token")" = 600 || fail "token file is not 0600"
lacks 'TEST_SECRET_DO_NOT_LOG' "$work/argv" "$work/log"

# Allowed run parameters are passed through.
export RUN_PARAMS='--protocol quic'
run_entry || fail "an allowed run parameter stopped the start"
has '--protocol' "$work/argv"
has 'quic' "$work/argv"

# Credential and metrics flags are refused before cloudflared starts, and the
# refused value is not echoed.
export RUN_PARAMS='--token=ADVERSARIAL_SECRET'
rm -f "$work/argv"
if run_entry; then fail "an unsafe run parameter reached cloudflared"; fi
test ! -e "$work/argv" || fail "cloudflared started with an unsafe run parameter"
lacks 'ADVERSARIAL_SECRET' "$work/log"
export RUN_PARAMS='--metrics=0.0.0.0:36500'
if run_entry; then fail "run_parameters opened the metrics listener publicly"; fi
test ! -e "$work/argv" || fail "cloudflared started with a public metrics listener"

# Unconfigured: idle without cloudflared, and drop a stale token file.
cat > "$work/bin/sleep" <<'STUB'
#!/bin/sh
exit 0
STUB
chmod +x "$work/bin/sleep"
export SIMULATE_UNCONFIGURED=1 WEBGUI_UNCONFIGURED_MARKER="$work/unconfigured" RUN_PARAMS=''
touch "$WEBGUI_UNCONFIGURED_MARKER"
printf '%s' 'STALE_TEST_TOKEN' > "$work/token"
rm -f "$work/argv"
run_entry || fail "the unconfigured idle path failed"
has 'not configured' "$work/log"
test ! -e "$work/token" || fail "a stale token file survived the unconfigured start"
test ! -e "$work/argv" || fail "cloudflared started while unconfigured"
echo 'PASS: token is confined to a 0600 file; argv and raw log are clean; metrics use loopback'
