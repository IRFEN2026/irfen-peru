#!/bin/sh
# IRFEN v0.9 — portable external ticker (any cron host outside GitHub Actions: a server crontab, a cloud scheduler).
# Same behaviour as worker.js: skip if the fallback is queued/running, else dispatch it on main. No other action.
#   */10 * * * *  GITHUB_TOKEN=... ENABLED=true /path/to/tick.sh >> /var/log/irfen-ticker.log 2>&1
set -eu
REPO="${REPO:-IRFEN2026/irfen-peru}"
WORKFLOW="${WORKFLOW:-v08-scheduler-fallback.yml}"
BASE="https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW"
H1="Authorization: Bearer $GITHUB_TOKEN"; H2="Accept: application/vnd.github+json"; H3="X-GitHub-Api-Version: 2022-11-28"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
for s in queued in_progress waiting pending requested; do
  n="$(curl -fsS -H "$H1" -H "$H2" -H "$H3" "$BASE/runs?branch=main&status=$s&per_page=5" | grep -c '"id":' || true)"
  if [ "${n:-0}" -gt 0 ]; then echo "$now FALLBACK_ACTIVE status=$s"; exit 0; fi
done
if [ "${ENABLED:-false}" != "true" ]; then echo "$now DRY_RUN"; exit 0; fi
code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "$H1" -H "$H2" -H "$H3" "$BASE/dispatches" -d '{"ref":"main"}')"
[ "$code" = "204" ] && echo "$now DISPATCH ok" || { echo "$now DISPATCH_FAILED http=$code"; exit 1; }
