#!/usr/bin/env bash
# IRFEN v0.9.1 · helpers for the definitive end-to-end test of #504 + #505 (RESEARCH_ONLY / TEST_ONLY).
# Sourced by .github/workflows/research-v091-integrated-e2e.yml. Every capture is the REAL v09-rain-north.yml of the
# integration code, dispatched ONCE by hand on an isolated research/v091-e2e-capture-* branch; nothing touches main,
# the real data branch, or any schedule. No date is modified: "new observation" means NASA published a newer half-hour.
set -euo pipefail

utcnow() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# capture LABEL VIEWER_REF -> exports <LABEL>_RUN, <LABEL>_DECIDE (notice line), <LABEL>_PHASE2 (notice line), <LABEL>_T0
capture() {
  local label=$1 viewer=$2 t0 id job log
  t0=$(utcnow)
  gh workflow run v09-rain-north.yml -R "$R" --ref "$CAP" -f "e2e_viewer_ref=$viewer" -f "e2e_test_data_branch=$TEST_DB"
  for _ in $(seq 1 60); do
    id=$(gh run list -R "$R" --workflow v09-rain-north.yml --branch "$CAP" --event workflow_dispatch -L 10 \
         --json databaseId,createdAt --jq "[.[]|select(.createdAt>=\"$t0\")]|sort_by(.createdAt)[0].databaseId // empty")
    [ -n "$id" ] && break; sleep 5
  done
  [ -n "$id" ] || { echo "::error::capture run for $label not found"; return 1; }
  gh run watch "$id" -R "$R" --interval 20 >/dev/null 2>&1 || true
  [ "$(gh api "repos/$R/actions/runs/$id" --jq .conclusion)" = success ] || { echo "::error::capture run $id ($label) did not succeed"; return 1; }
  [ "$(gh api "repos/$R/actions/runs/$id" --jq .head_branch)" = "$CAP" ] || { echo "::error::capture ran outside the isolated branch"; return 1; }
  job=$(gh api "repos/$R/actions/runs/$id/jobs" --jq '.jobs[0].id')
  log=$(gh api "repos/$R/actions/jobs/$job/logs")
  local dec p2 gate
  # GitHub renders `::notice title=X::msg` as `##[notice]msg` in the raw log; the script text (echoed as the run
  # command) never contains these literal results, so the first match is the real output.
  dec=$(grep -m1 -oE 'last_obs_end=[^ ]+ age_h=.*' <<<"$log" || true)
  p2=$(grep -m1 -oE '\{"at_utc": "[^"]+", "action": "[A-Z_]+".*\}' <<<"$log" || echo "(fase 2 no ejecutada)")
  gate=$(grep -m1 -oE 'after-capture rebuild request: (true|false).*' <<<"$log" || true)
  [ -n "$dec" ] || { echo "::error::no freshness decision in capture run $id"; return 1; }
  {
    echo "${label}_RUN=$id"; echo "${label}_T0=$t0"
    echo "${label}_DECIDE=$dec"; echo "${label}_PHASE2=$p2"; echo "${label}_GATE=$gate"
  } >> "$GITHUB_ENV"
  printf '| %s | run %s | %s | %s | %s |\n' "$label" "$id" "$gate" "$dec" "$p2" >> "$GITHUB_STEP_SUMMARY"
  echo "$label run=$id"; echo "  gate: $gate"; echo "  decide: $dec"; echo "  phase2: $p2"
  export LAST_DECIDE=" $dec " LAST_PHASE2="$p2" LAST_RUN="$id" LAST_T0="$t0"
}

# rebuild runs of the viewer created on the integration branch since $1
rebuilds_since() {
  gh run list -R "$R" --workflow v091-live-refresh.yml --branch "$INT" --event workflow_dispatch -L 20 \
    --json databaseId,createdAt --jq "[.[]|select(.createdAt>=\"$1\")]|map(.databaseId)|join(\" \")"
}

ledger_at() { git fetch -q --no-tags origin "$CAP" && git show "FETCH_HEAD:data/v09/rain/freshness_ledger_v0_1.json"; }
