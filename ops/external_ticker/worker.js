// IRFEN v0.9 — external ticker for the controlled scheduler fallback (TEST_ONLY operations).
//
// Runs OUTSIDE GitHub Actions (Cloudflare Workers Cron Trigger, see wrangler.toml). Every tick it asks GitHub to run
// ONE workflow on main: .github/workflows/v08-scheduler-fallback.yml. That workflow (scripts/scheduler_fallback.py)
// decides, workflow by workflow, whether a collector is stale; it never dispatches a workflow that is queued or
// running, or that ran within its cooldown, or that is not on main. This ticker holds no science and no logic beyond:
//
//   1. skip the tick if the fallback itself is already queued or running (no pile-up of fallback runs);
//   2. otherwise POST workflow_dispatch(ref=main) for the fallback;
//   3. log the outcome (Workers logs). It never retries in a loop and never touches data, branches or guards.
//
// Secrets/vars (set with `wrangler secret put GITHUB_TOKEN`; vars in wrangler.toml):
//   GITHUB_TOKEN  fine-grained token of the repository owner, this repository only, permission "Actions: Read and
//                 write" and nothing else, with an expiry date.
//   REPO          "IRFEN2026/irfen-peru"
//   WORKFLOW      "v08-scheduler-fallback.yml"
//   ENABLED       "true" to dispatch; anything else = dry run (logs what it would do).
//
// Enable only after the per-workflow fallback (PR #372) is on main: the previous version of that workflow applies a
// global 4-hour gate.

const API = "https://api.github.com";
const ACTIVE = ["queued", "in_progress", "waiting", "requested", "pending"];

export function headers(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "irfen-v09-external-ticker",
  };
}

// Pure decision, unit-tested: activeRuns = runs of the fallback workflow on main with an active status.
export function decideTick(enabled, activeRuns) {
  if (activeRuns.length > 0) return { dispatch: false, reason: `FALLBACK_ACTIVE: ${activeRuns.length} run(s) queued or running` };
  if (!enabled) return { dispatch: false, reason: "DRY_RUN: ENABLED is not 'true'" };
  return { dispatch: true, reason: "DISPATCH: fallback idle" };
}

export const ALLOWED = { REPO: "IRFEN2026/irfen-peru", WORKFLOW: "v08-scheduler-fallback.yml" };

// Fail closed: any error, missing secret, unexpected configuration or unexpected API answer means no dispatch.
export async function tick(env, fetchImpl = fetch) {
  try {
    return await tickUnsafe(env, fetchImpl);
  } catch (e) {
    return { dispatched: false, reason: `ERROR: ${String((e && e.message) || e).slice(0, 120)}` };
  }
}

async function tickUnsafe(env, fetchImpl) {
  if (!env.GITHUB_TOKEN) return { dispatched: false, reason: "MISSING_TOKEN" };
  if (env.REPO !== ALLOWED.REPO || env.WORKFLOW !== ALLOWED.WORKFLOW) return { dispatched: false, reason: "CONFIG_REFUSED" };
  const base = `${API}/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}`;
  const active = [];
  for (const status of ["queued", "in_progress", "waiting", "pending", "requested"]) {
    const r = await fetchImpl(`${base}/runs?branch=main&status=${status}&per_page=5`, { headers: headers(env.GITHUB_TOKEN) });
    if (!r.ok) return { dispatched: false, reason: `LIST_FAILED: HTTP ${r.status} for status=${status}` };
    const body = await r.json();
    if (!body || !Array.isArray(body.workflow_runs)) return { dispatched: false, reason: `LIST_UNEXPECTED for status=${status}` };
    active.push(...body.workflow_runs.filter((x) => ACTIVE.includes(x.status)));
  }
  const d = decideTick(env.ENABLED === "true", active);
  if (!d.dispatch) return { dispatched: false, reason: d.reason };
  const r = await fetchImpl(`${base}/dispatches`, {
    method: "POST",
    headers: { ...headers(env.GITHUB_TOKEN), "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" }),
  });
  return r.status === 204 ? { dispatched: true, reason: d.reason } : { dispatched: false, reason: `DISPATCH_FAILED: HTTP ${r.status}` };
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(tick(env).then((res) => console.log(JSON.stringify({ at: new Date(event.scheduledTime).toISOString(), ...res }))));
  },
  async fetch() {
    return new Response("Not found", { status: 404 }); // no public HTTP endpoint
  },
};
