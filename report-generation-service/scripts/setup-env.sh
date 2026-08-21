#!/usr/bin/env sh
#
# Creates the .env file for the Report Generation Service, correctly, without anybody having
# to copy a value by hand.
#
# It works out which docker network OpenMRS is on, checks that the network really exists,
# generates the shared token if there isn't one yet, and writes .env. Then it tells you
# exactly what to run next.
#
# Why this exists: the two values in .env are the only things a person has to get right, and
# both are easy to get wrong in a way docker reports badly.
#
#   * The network must be given by NAME. `docker network ls` shows the ID in the first column,
#     and pasting that ID produces the useless error
#         network <64-hex-id> declared as external, but could not be found
#     because compose only ever looks names up, never IDs.
#   * A container can be attached to more than one network, so a naive one-line inspect can
#     silently concatenate two names into one string that matches nothing.
#
# Usage:
#     sh scripts/setup-env.sh              # assumes the OpenMRS container is `openmrs-app`
#     sh scripts/setup-env.sh my-openmrs   # or name it yourself

set -eu

CONTAINER="${1:-openmrs-app}"
ENV_FILE="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)/.env"

say()  { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

say "=== Report Generation Service - environment setup ==="
say ""

# ---------------------------------------------------------------- docker ----

command -v docker >/dev/null 2>&1 || fail "docker is not installed, or not on your PATH."
docker info >/dev/null 2>&1 || fail "docker is installed but not running. Start it and try again."

docker inspect "$CONTAINER" >/dev/null 2>&1 || {
    say "Could not find a container called '$CONTAINER'."
    say ""
    say "These containers are running right now:"
    docker ps --format '  {{.Names}}'
    say ""
    fail "Re-run this script with the right name, e.g.:  sh scripts/setup-env.sh <name>"
}

say "OpenMRS container : $CONTAINER"

# --------------------------------------------------------------- network ----

# One name per line. The newline matters: a container on two networks would otherwise come
# back as a single concatenated string that matches no real network.
NETWORKS="$(docker inspect \
    -f '{{range $name, $conf := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' \
    "$CONTAINER" | grep -v '^$' || true)"

[ -n "$NETWORKS" ] || fail "'$CONTAINER' is not attached to any docker network."

COUNT="$(printf '%s\n' "$NETWORKS" | wc -l | tr -d ' ')"

if [ "$COUNT" -eq 1 ]; then
    NETWORK="$NETWORKS"
else
    say ""
    say "'$CONTAINER' is on more than one network:"
    printf '  - %s\n' $NETWORKS
    say ""
    # 'bridge' is docker's shared default network; anything else is the project's own, which
    # is the one the renderer should join.
    NETWORK="$(printf '%s\n' "$NETWORKS" | grep -v '^bridge$' | head -n 1)"
    [ -n "$NETWORK" ] || NETWORK="$(printf '%s\n' "$NETWORKS" | head -n 1)"
    say "Choosing: $NETWORK"
    say "(If that is wrong, edit OPENMRS_NETWORK in .env afterwards.)"
fi

# Prove the name resolves as a name, which is the exact thing compose will do.
docker network inspect "$NETWORK" >/dev/null 2>&1 \
    || fail "Found network '$NETWORK' but docker cannot look it up by name."

say "Docker network    : $NETWORK"

# ----------------------------------------------------------------- token ----

EXISTING_TOKEN=""
if [ -f "$ENV_FILE" ]; then
    EXISTING_TOKEN="$(sed -n 's/^MEDREPORT_RGS_TOKEN=//p' "$ENV_FILE" | head -n 1)"
fi

if [ -n "$EXISTING_TOKEN" ]; then
    TOKEN="$EXISTING_TOKEN"
    say "Shared token      : kept the existing one (unchanged)"
    TOKEN_IS_NEW=0
else
    if command -v openssl >/dev/null 2>&1; then
        TOKEN="$(openssl rand -hex 32)"
    else
        TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    fi
    say "Shared token      : generated a new one"
    TOKEN_IS_NEW=1
fi

# ------------------------------------------------------------------ write ---

# Written as a full `if`, not `[ ... ] && cp`: under `set -e` a false test makes the whole
# && chain return non-zero and the script would exit right here on a first install.
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$ENV_FILE.backup"
fi

cat > "$ENV_FILE" <<EOF
# Written by scripts/setup-env.sh - safe to re-run.

# Shared secret between OpenMRS and this service. The SAME value must be pasted into the
# OpenMRS global property  medreport.renderService.token
MEDREPORT_RGS_TOKEN=$TOKEN

# The docker network the OpenMRS container is already on. Must be the network NAME, never
# the ID that 'docker network ls' shows in its first column.
OPENMRS_NETWORK=$NETWORK
EOF

chmod 600 "$ENV_FILE" 2>/dev/null || true

say ""
say "Wrote $ENV_FILE"
if [ -f "$ENV_FILE.backup" ]; then
    say "(previous version saved as .env.backup)"
fi

# ------------------------------------------------------------------- next ---

say ""
say "-------------------------------------------------------------------"
say "NEXT STEPS"
say ""
say "1. Start the service:"
say "     docker compose up --build -d"
say ""
say "2. Check OpenMRS can reach it (this is the step people skip):"
say "     docker exec $CONTAINER curl -fsS http://medreport-rgs:8300/health"
say ""
if [ "${TOKEN_IS_NEW:-0}" -eq 1 ]; then
    say "3. In OpenMRS: System Administration -> Advanced Settings,"
    say "   set  medreport.renderService.token  to exactly this value:"
    say ""
    say "     $TOKEN"
    say ""
    say "   (also shown by:  grep MEDREPORT_RGS_TOKEN .env )"
else
    say "3. The token was already set. If OpenMRS still reports a token error, compare:"
    say "     grep MEDREPORT_RGS_TOKEN .env"
    say "   against medreport.renderService.token in Advanced Settings."
fi
say "-------------------------------------------------------------------"
