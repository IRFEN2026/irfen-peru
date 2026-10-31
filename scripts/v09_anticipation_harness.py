#!/usr/bin/env python3
"""IRFEN v0.9 · arnés del protocolo v0.3 de anticipación (RESEARCH_ONLY / TEST_ONLY). Sin umbrales ni alertas.

Lee `config/v09_anticipation_protocol_v0_3.json` y solo admite lo que allí está fijado:
* objetivo = caudal o nivel MEDIDO con paso ≤ 1 h, hora y zona horaria explícitas; si no, `NO_EVALUABLE`;
* cada predictor se construye con registros cuya hora de DISPONIBILIDAD (observación + latencia) es ≤ t; cada fila
  guarda la hora máxima usada y se comprueba con una aserción;
* IMERG Final está prohibido como predictor;
* modelos B0 (persistencia), B1 (tendencia local), B2 (B1 + estación aguas arriba; línea base de referencia) y
  M = B2 + ln(1 + R_k), k = 6 y 24 h;
* validación dejando un episodio fuera, episodios separados ≥ 7 días; nada se ajusta con el episodio de evaluación;
* ΔMSE = MSE_B2 − MSE_M con bootstrap por bloques de 48 h, placebo de lluvia desplazada ≥ 7 días, latencia +2 h y Holm.

Con los datos disponibles hoy (medias diarias PECHP) el resultado es `NO_EVALUABLE` para todos los horizontes; el
arnés se comprueba con series de juguete SOLO en las pruebas (nunca como observaciones).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "config/v09_anticipation_protocol_v0_3.json"
OUT = ROOT / "data/v09/research/anticipation/anticipation_evaluation_v0_1.json"
H = 3600


class ProtocolError(ValueError):
    pass


class Series:
    """A time series with its data category and availability latency. times = observation END, UTC seconds."""

    def __init__(self, id: str, category: str, times, values, latency_s: int, product: str = "", tz_declared: bool = True,
                 statistic: str = "INSTANTANEO", meta: dict | None = None):
        self.id, self.category, self.latency_s, self.product = id, category, int(latency_s), product
        self.tz_declared, self.statistic, self.meta = tz_declared, statistic, meta or {}
        self.times, self.values = times, values
        self.__post_init__()

    def __post_init__(self):
        o = np.argsort(self.times, kind="stable")
        self.times = np.asarray(self.times, np.int64)[o]
        self.values = np.asarray(self.values, float)[o]
        self._cache: dict = {}

    def step_hours(self) -> float | None:
        if "step" not in self._cache:
            self._cache["step"] = None if len(self.times) < 3 else float(np.median(np.diff(self.times))) / H
        return self._cache["step"]

    def avail(self, extra_latency_s: int) -> np.ndarray:
        k = ("avail", extra_latency_s)
        if k not in self._cache:
            self._cache[k] = self.times + self.latency_s + extra_latency_s
        return self._cache[k]


def load_protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def check_target(s: Series, proto: dict) -> str | None:
    req = proto["target_requirements"]
    if s.category != req["category"]:
        return f"CATEGORIA_NO_ADMITIDA_COMO_OBJETIVO ({s.category})"
    if s.statistic == "MEDIA_DIARIA" and not req["daily_means_allowed"]:
        return "MEDIAS_DIARIAS: no permiten horizontes de 3–24 h y no se desagregan"
    st = s.step_hours()
    if st is None or st > req["max_time_step_hours"]:
        return f"PASO_TEMPORAL_INSUFICIENTE ({st} h > {req['max_time_step_hours']} h)"
    if not s.tz_declared:
        return "ZONA_HORARIA_NO_DECLARADA"
    return None


def check_rain(s: Series) -> str | None:
    if s.category != "LLUVIA_REGISTRADA":
        return f"CATEGORIA_NO_ES_LLUVIA ({s.category})"
    if "FINAL" in s.product.upper() or s.product.upper().endswith("IMERGHH") or s.product.upper().endswith("IMERGDF"):
        return "IMERG_FINAL_PROHIBIDO_COMO_PREDICTOR (ORACULO_NO_OPERATIVO)"
    return None


def last_available(s: Series, t: int, extra_latency_s: int = 0):
    """Latest record whose availability time (obs end + latency) is ≤ t. Returns (value, obs_time) or (nan, None)."""
    i = int(np.searchsorted(s.avail(extra_latency_s), t, side="right")) - 1
    if i < 0:
        return np.nan, None
    return float(s.values[i]), int(s.times[i])


def rain_accum(s: Series, t: int, k_h: int, extra_latency_s: int = 0):
    """Sum of rain records fully observed and AVAILABLE by t over the k hours ending at the last available instant.
    Incomplete coverage → nan (unknown, never 0)."""
    end = t - s.latency_s - extra_latency_s
    start = end - k_h * H
    i0 = int(np.searchsorted(s.times, start, side="right"))
    i1 = int(np.searchsorted(s.times, end, side="right"))
    step = s.step_hours() or 0.5
    need = int(round(k_h / step))
    vals = s.values[i0:i1]
    if i1 - i0 < need or np.isnan(vals).any():
        return np.nan, None
    return float(vals.sum()), int(s.times[i1 - 1])


def target_at(s: Series, t: int):
    i = int(np.searchsorted(s.times, t))
    if i < len(s.times) and int(s.times[i]) == t:
        return float(s.values[i])
    return np.nan


def xf(v):
    return np.log1p(v) if v == v else np.nan


def design(target: Series, upstream: Series | None, rain: Series | None, issue_times, h_h: int, k_h: int, extra_lat_s: int = 0):
    rows, used_max = [], []
    for t in issue_times:
        x0, t0 = last_available(target, t, extra_lat_s)
        xh, _ = last_available(target, t - h_h * H, extra_lat_s)
        x24, _ = last_available(target, t - 24 * H, extra_lat_s)
        y = target_at(target, t + h_h * H)
        feats = [xf(x0), xf(x0) - xf(xh), xf(x0) - xf(x24)]
        tmax = [t0]
        if upstream is not None:
            u0, tu = last_available(upstream, t, extra_lat_s)
            uh, _ = last_available(upstream, t - h_h * H, extra_lat_s)
            feats += [xf(u0) - xf(uh), xf(u0)]
            tmax.append(tu)
        if rain is not None:
            r, tr = rain_accum(rain, t, k_h, extra_lat_s)
            feats.append(np.log1p(r) if r == r else np.nan)
            tmax.append(tr)
        if any(v is None for v in tmax) or any(np.isnan(feats)) or np.isnan(xf(y)):
            continue
        used = max(tmax)
        assert used <= t, "fuga temporal: un predictor usa un dato no disponible en t"
        rows.append(feats + [xf(y), t])
        used_max.append(used)
    a = np.array(rows, float) if rows else np.zeros((0, 9))
    return a, used_max


def fit_predict(Xtr, ytr, Xev):
    A = np.column_stack([np.ones(len(Xtr)), Xtr])
    beta, *_ = np.linalg.lstsq(A, ytr, rcond=None)
    return np.column_stack([np.ones(len(Xev)), Xev]) @ beta


def block_bootstrap_delta(e_b, e_m, block=48, reps=2000, seed=20261031):
    n = len(e_b)
    if n < block * 2:
        return None
    rng = np.random.default_rng(seed)
    d = e_b - e_m
    starts = np.arange(0, n - block + 1)
    nb = int(np.ceil(n / block))
    stats = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, nb)])[:n]
        stats.append(d[idx].mean())
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def holm(pvals: dict) -> dict:
    items = sorted((v, k) for k, v in pvals.items() if v is not None)
    m, out, run = len(items), {}, 0.0
    for i, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def episode_times(ep, h_h, k_h):
    t0 = int(datetime.fromisoformat(ep["start"]).timestamp()) + (24 + k_h) * H
    t1 = int(datetime.fromisoformat(ep["end"]).timestamp()) - h_h * H
    return list(range(t0, t1 + 1, H))


def check_episodes(eps):
    se = sorted((datetime.fromisoformat(e["start"]).timestamp(), datetime.fromisoformat(e["end"]).timestamp(), e["id"]) for e in eps)
    for (a0, a1, ia), (b0, b1, ib) in zip(se, se[1:]):
        if b0 - a1 < 7 * 86400:
            raise ProtocolError(f"episodios {ia} y {ib} separados < 7 días")


def shifted(rain: Series, days: int) -> Series:
    span = int(rain.times.max() - rain.times.min()) + int(np.median(np.diff(rain.times)))
    t = (rain.times - rain.times.min() + days * 86400) % span + rain.times.min()
    o = np.argsort(t)
    return Series(rain.id + f"_placebo{days}", rain.category, t[o], rain.values[o], rain.latency_s, rain.product)


def evaluate_pair(target: Series, upstream: Series | None, rain: Series | None, episodes: list, proto: dict) -> dict:
    why = check_target(target, proto)
    if why:
        return dict(status="NO_EVALUABLE", reason=why)
    if upstream is not None and check_target(upstream, proto):
        return dict(status="NO_EVALUABLE", reason="ESTACION_AGUAS_ARRIBA: " + check_target(upstream, proto))
    if rain is not None and check_rain(rain):
        return dict(status="NO_EVALUABLE", reason=check_rain(rain))
    if len(episodes) < 2:
        return dict(status="NO_EVALUABLE", reason="MENOS_DE_DOS_EPISODIOS")
    check_episodes(episodes)
    extra = proto["availability_latency_hours"]["sensitivity_extra_hours"][-1] * H
    res, pv = {}, {}
    for h_h in proto["horizons_hours"]:
        for k_h in proto["rain_accumulations_hours"]:
            key = f"h{h_h}_k{k_h}"
            per_ep = []
            for ev in episodes:
                tr_eps = [e for e in episodes if e["id"] != ev["id"]]
                out = {}
                for lat_extra in (0, extra):
                    def build(r):
                        Dtr = [design(target, upstream, r, episode_times(e, h_h, k_h), h_h, k_h, lat_extra)[0] for e in tr_eps]
                        Dtr = np.vstack([d for d in Dtr if len(d)]) if any(len(d) for d in Dtr) else np.zeros((0, 9))
                        Dev, used = design(target, upstream, r, episode_times(ev, h_h, k_h), h_h, k_h, lat_extra)
                        return Dtr, Dev, used
                    Dtr, Dev, used = build(rain)
                    nb = 5 if upstream is not None else 3
                    if len(Dtr) < 50 or len(Dev) < 96:
                        out[lat_extra] = dict(status="DATOS_INSUFICIENTES", n_train=len(Dtr), n_eval=len(Dev))
                        continue
                    ytr, yev = Dtr[:, -2], Dev[:, -2]
                    pers = Dev[:, 0]
                    pb = fit_predict(Dtr[:, :nb], ytr - Dtr[:, 0], Dev[:, :nb]) + pers
                    pm = fit_predict(Dtr[:, :nb + 1], ytr - Dtr[:, 0], Dev[:, :nb + 1]) + pers
                    eb, em = (yev - pb) ** 2, (yev - pm) ** 2
                    d_obs = float(eb.mean() - em.mean())
                    ci = block_bootstrap_delta(eb, em)
                    rec = dict(n_train=len(Dtr), n_eval=len(Dev), mse_B0=float(((yev - pers) ** 2).mean()), mse_B2=float(eb.mean()),
                               mse_M=float(em.mean()), delta_mse=d_obs, ci95=ci, skill=1 - float(em.mean()) / float(eb.mean()),
                               max_feature_time_minus_issue_s=int(max(u - t for u, t in zip(used, Dev[:, -1].astype(int)))))
                    if lat_extra == 0 and rain is not None:
                        null = []
                        span_days = int((rain.times.max() - rain.times.min()) / 86400)
                        for sd in range(7, max(8, span_days - 6)):
                            Dtr_p, Dev_p, _ = build(shifted(rain, sd))
                            if len(Dtr_p) < 50 or len(Dev_p) < 96:
                                continue
                            ppm = fit_predict(Dtr_p[:, :nb + 1], Dtr_p[:, -2] - Dtr_p[:, 0], Dev_p[:, :nb + 1]) + Dev_p[:, 0]
                            ppb = fit_predict(Dtr_p[:, :nb], Dtr_p[:, -2] - Dtr_p[:, 0], Dev_p[:, :nb]) + Dev_p[:, 0]
                            null.append(float(((Dev_p[:, -2] - ppb) ** 2).mean() - ((Dev_p[:, -2] - ppm) ** 2).mean()))
                        rec["placebo_n"] = len(null)
                        rec["placebo_p95"] = float(np.percentile(null, 95)) if null else None
                        rec["placebo_p"] = (sum(x >= d_obs for x in null) + 1) / (len(null) + 1) if null else None
                    out[lat_extra] = rec
                per_ep.append(dict(eval_episode=ev["id"], latency_plus0=out.get(0), latency_plus_extra=out.get(extra)))
            ok = [e for e in per_ep if (e["latency_plus0"] or {}).get("ci95") and e["latency_plus0"]["ci95"][0] > 0
                  and e["latency_plus0"].get("placebo_p95") is not None and e["latency_plus0"]["delta_mse"] > e["latency_plus0"]["placebo_p95"]
                  and (e["latency_plus_extra"] or {}).get("ci95") and e["latency_plus_extra"]["ci95"][0] > 0]
            ps = [e["latency_plus0"].get("placebo_p") for e in per_ep if (e["latency_plus0"] or {}).get("placebo_p") is not None]
            pv[key] = max(ps) if ps else None
            res[key] = dict(horizon_h=h_h, rain_k_h=k_h, per_episode=per_ep, episodes_meeting_ci_placebo_latency=len(ok))
    adj = holm(pv)
    for key, r in res.items():
        r["placebo_p_max_over_episodes"] = pv[key]
        r["holm_p"] = adj.get(key)
        r["verdict"] = ("MEJORA_DEMOSTRABLE" if r["episodes_meeting_ci_placebo_latency"] >= 2 and (adj.get(key) or 1) < 0.05
                        else "RESULTADO_NEGATIVO_O_NO_CONCLUYENTE")
    return dict(status="EVALUADO", results=res)


def current_inputs_report(proto: dict) -> dict:
    """What can be evaluated TODAY with archived data: only PECHP daily means → NO_EVALUABLE, stated per target."""
    pechp = json.loads((ROOT / "data/v09/research/historical/pechp_daily_v0_1.json").read_text(encoding="utf-8"))
    cols = sorted({c for m in pechp["months"] for t in m["tables"].values() if t.get("status") == "OK"
                   for d in (t.get("days") or {}).values() for c in d["values"]})
    targets = []
    for p in proto["upstream_pairs"]:
        if p["upstream"] is None:
            targets.append(dict(target=p["target"], status="FUERA_DE_ALCANCE", reason=p["regime_rule"]))
            continue
        s = Series(p["target"], "CAUDAL_O_NIVEL_MEDIDO", np.arange(0, 40 * 86400, 86400, dtype=np.int64), np.ones(40), 0,
                   statistic="MEDIA_DIARIA", meta=dict(note="estructura de los datos archivados (medias diarias PECHP)"))
        why = check_target(s, proto)
        targets.append(dict(target=p["target"], upstream=p["upstream"], status="NO_EVALUABLE", reason=why,
                            horizons_h=proto["horizons_hours"],
                            archived_resolution="MEDIA_DIARIA (PECHP) o sin serie" ))
    return dict(schema_version="irfen_v09_anticipation_evaluation_v0_1", protocol="v0.3", deployment_status="RESEARCH_ONLY",
                test_mode="TEST_ONLY", production_use=False, operational_alerting_enabled=False, activation_gate="BLOCKED",
                decision_thresholds=None, hydraulic_factors=None, missing_data_rule="UNKNOWN_NOT_LOW_RISK",
                archived_flow_columns=cols, targets=targets,
                conclusion="Ningún horizonte de 3, 6, 12 o 24 h es evaluable con los datos archivados: solo hay medias diarias. "
                           "No se ha hecho ninguna comparación de anticipación; la mejora no está demostrada ni refutada.",
                next_experiment="Ejecutar evaluate_pair() con series horarias oficiales (SENAMHI/PECHP) y lluvia IMERG Early V07 de 30 min "
                                "sobre las cuencas VALIDADA_EXPERIMENTAL, con los episodios fijados antes de abrir los datos.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(current_inputs_report(load_protocol()), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
