#!/bin/sh
set -eu
MLH_PRIVATE_ACCESS_TOKEN="$(cat /run/secrets/private_access_token)"
MLH_BASIC_AUTH_HASH="$(cat /run/secrets/web_basic_auth_hash)"
test -n "$MLH_PRIVATE_ACCESS_TOKEN"
test -n "$MLH_BASIC_AUTH_HASH"
export MLH_PRIVATE_ACCESS_TOKEN
export MLH_BASIC_AUTH_HASH
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
