#!/usr/bin/env bash
# The CI workflow, run locally.
#
# Not a convenience wrapper around `make test`. It mirrors what
# .github/workflows/ci.yml does, and the differences from `make test` are
# the whole point:
#
#   - it installs into a THROWAWAY database, so it cannot pass because the
#     dev database happens to be in a good state. `make test` once reported
#     "0 failed, 0 error(s) of 0 tests" and exited 0 because dw_git was
#     uninstalled there — a suite with nothing in it looks exactly like a
#     suite that passed.
#   - it greps the INSTALL log for failures Odoo boots straight through.
#   - it pins the browser-tour count to the tours registered on disk.
#
# Usage: make ci
set -uo pipefail

DB="${CI_DB:-ci_local}"
DBFLAGS="--db_host=postgres --db_user=odoo --db_password=odoo --workers=0"
COMPOSE="docker compose"
LOGS="$(mktemp -d)"
FAILED=0

# Odoo logs "Closed N connections" before postgres has released them, so a
# bare DROP loses a race against its own teardown and fails with "database
# is being accessed by other users". Silencing that failure is worse than
# the race: the throwaway database survives, and a SECOND database makes
# Odoo serve /web/database/selector instead of the login form, which fails
# every browser flow in `make qa` at "Password: element never appeared".
# That is exactly what happened after the first run of this script.
drop_db() {
    # Stopping odoo first is not belt-and-braces, it is required: its
    # connection pool reconnects faster than pg_terminate_backend can clear
    # it, so a terminate-then-drop loses the race and the database survives.
    # docs/RELEASING.md prescribes the same dance for release_check.
    #
    # Leaving it behind is not cosmetic. A SECOND database makes Odoo serve
    # /web/database/selector instead of the login form, and every browser
    # flow in `make qa` then fails at "Password: element never appeared" —
    # which is exactly how the first run of this script broke the release
    # gate that came after it.
    docker compose stop odoo >/dev/null 2>&1
    docker compose exec -T postgres dropdb -U odoo --if-exists "$DB" >/dev/null 2>&1
    docker compose start odoo >/dev/null 2>&1
    for _ in $(seq 1 30); do
        docker compose exec -T odoo true >/dev/null 2>&1 && break
        sleep 1
    done
    if docker compose exec -T postgres psql -U odoo -lqt 2>/dev/null \
            | cut -d"|" -f1 | tr -d " " | grep -qx "$DB"; then
        printf '\033[31mWARNING\033[0m  could not drop %s — drop it before running make qa\n' "$DB"
        return 1
    fi
    return 0
}

step()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
fail()  { printf '\033[31mFAIL\033[0m  %s\n' "$1"; FAILED=1; }
ok()    { printf '\033[32mok\033[0m    %s\n' "$1"; }

step "Static checks"
for target in xml lint assets; do
    if make "$target" >"$LOGS/$target.log" 2>&1; then
        ok "$target"
    else
        fail "$target"; tail -20 "$LOGS/$target.log"
    fi
done

step "Install into a throwaway database ($DB)"
drop_db
if $COMPOSE exec -T odoo odoo -d "$DB" -i dw_git --stop-after-init $DBFLAGS \
        >"$LOGS/install.log" 2>&1; then
    ok "module installs from scratch"
else
    fail "install failed"; tail -25 "$LOGS/install.log"
fi

step "Install log is free of latent failures"
# Odoo boots straight through every one of these; each hid a real defect.
for pattern in "Invalid field" "Template not found" "have no access rules" \
               "unknown parameter" "CRITICAL"; do
    if grep -q "$pattern" "$LOGS/install.log"; then
        fail "install log contains: $pattern"
        grep "$pattern" "$LOGS/install.log" | head -3
    fi
done
[ "$FAILED" -eq 0 ] && ok "install log clean"

step "Test suite"
$COMPOSE exec -T odoo odoo -d "$DB" --test-enable --test-tags /dw_git \
    --stop-after-init --http-port=8070 $DBFLAGS >"$LOGS/test.log" 2>&1

if ! grep -qE "odoo.tests.stats: dw_git: [0-9]+ tests" "$LOGS/test.log"; then
    fail "no dw_git tests ran at all"
elif ! grep -q "0 failed, 0 error(s)" "$LOGS/test.log"; then
    fail "test failures"
    grep -E "^(FAIL|ERROR): |tests when loading" "$LOGS/test.log" | head -10
    grep -oE "(FAIL|ERROR): Test[A-Za-z]+\.[a-z0-9_]+" "$LOGS/test.log" | sort -u
else
    ok "$(grep -oE 'dw_git: [0-9]+ tests' "$LOGS/test.log" | tail -1)"
fi

step "Browser tours actually ran"
if grep -qE "skipped .*(Chrome|websocket-client|devtools port)" "$LOGS/test.log"; then
    fail "tours were SKIPPED, not passed"
    grep -E "skipped .*(Chrome|websocket-client)" "$LOGS/test.log" | head -3
else
    # Odoo logs success as "TOUR <name> SUCCEEDED", in capitals.
    ran=$(grep -ciE "TOUR [a-z_]+ SUCCEEDED" "$LOGS/test.log" || true)
    registered=$(grep -rhoE 'web_tour\.tours"\)\.add\("[a-z_]+' \
                 dw_git/static/src/tours/*.js | wc -l | tr -d ' ')
    # Pinned, not ">0": six of seven silently ceasing to run is the shape
    # this exists to catch, and a tour that never runs fails nothing.
    if [ "$ran" -lt "$registered" ]; then
        fail "only $ran of $registered browser tours succeeded"
        comm -13 \
          <(grep -oiE "TOUR [a-z_]+ SUCCEEDED" "$LOGS/test.log" \
            | sed 's/[Tt][Oo][Uu][Rr] //;s/ SUCCEEDED//' | sort -u) \
          <(grep -rhoE 'web_tour\.tours"\)\.add\("[a-z_]+' \
            dw_git/static/src/tours/*.js | sed 's/.*add("//' | sort) \
          | sed 's/^/        never ran: /'
    else
        ok "$ran of $registered browser tours succeeded"
    fi
fi

step "Result"
drop_db || FAILED=1
if [ "$FAILED" -eq 0 ]; then
    printf '\033[32mALL CI GATES PASSED\033[0m  (logs: %s)\n' "$LOGS"
else
    printf '\033[31mCI GATES FAILED\033[0m  (logs: %s)\n' "$LOGS"
fi
exit "$FAILED"
