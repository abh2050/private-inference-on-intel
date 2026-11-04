#!/usr/bin/env python3
"""Turns a results/<run>/ folder into the headline numbers: SLA capacity, $/1M tokens, AMX gain, routing what-if.
Usage: python3 analyze.py results/<run> [--usd-per-hour 1.90]
Writes results/<run>/summary.md and summary.json.
"""
import argparse, csv, json, pathlib

SLA = {"ttft_p95_s": 2.0, "min_user_tok_s": 10.0}   # fixed before the run; see RUNBOOK.md


def load(d, label):
    f = d / f"bench-{label}.json"
    return json.loads(f.read_text())["levels"] if f.exists() else []


def per_user_tok_s(r):  # decode speed one user sees
    return round(1000 / r["tpot_p50_ms"], 1) if r.get("tpot_p50_ms") else 0


def meets(r):
    return (r["failed"] == 0 and r["ttft_p95_s"] is not None and r["ttft_p95_s"] <= SLA["ttft_p95_s"]
            and per_user_tok_s(r) >= SLA["min_user_tok_s"])


def usd_per_m(r, usd_h):
    return round(usd_h / (r["output_tok_per_s"] * 3600) * 1e6, 2) if r["output_tok_per_s"] else None


def best(levels):  # highest concurrency that meets the SLA
    ok = [r for r in levels if meets(r)]
    return max(ok, key=lambda r: r["concurrency"]) if ok else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--usd-per-hour", type=float, default=1.90)
    a = ap.parse_args(); d = pathlib.Path(a.run); usd = a.usd_per_hour
    out, md = {"usd_per_hour": usd, "sla": SLA}, ["# Results summary", f"Server cost assumed: ${usd}/h. SLA: p95 TTFT ≤ {SLA['ttft_p95_s']} s, ≥ {SLA['min_user_tok_s']} tok/s per user, 0 errors.", ""]

    # E1: timeline
    tl = d / "timeline.csv"
    if tl.exists():
        rows = list(csv.DictReader(tl.open()))
        md += ["## E1: time to first request", "| phase | seconds | exit |", "|---|---|---|"]
        md += [f"| {r['phase']} | {r['seconds']} | {r['exit']} |" for r in rows]
        upto = 0
        for r in rows:
            upto += int(r["seconds"])
            if r["phase"] == "deploy_qwen3-0-6b": break
        out["e1_minutes_to_first_request"] = round(upto / 60, 1)
        md += [f"\n**Bare server → first served model: {out['e1_minutes_to_first_request']} min** (sum of phases, excluding server boot)."]
        fr = d / "friction.txt"
        if fr.exists(): md += ["", "```", fr.read_text().strip(), "```"]

    # E2-E4: sweeps
    runs = {"E2 Qwen3-0.6B, AMX on": "E2-qwen0.6b-amx", "E3 Qwen3-0.6B, AMX off": "E3-qwen0.6b-noamx",
            "E4 Qwen2.5-3B, AMX on": "E4-qwen2.5-3b-amx"}
    out["sweeps"] = {}
    for title, label in runs.items():
        lv = load(d, label)
        if not lv: continue
        md += ["", f"## {title}", "| users | ok/total | req/s | out tok/s | TTFT p50 | TTFT p95 | tok/s per user | $/1M out tok | SLA |",
               "|---|---|---|---|---|---|---|---|---|"]
        for r in lv:
            md.append(f"| {r['concurrency']} | {r['succeeded']}/{r['requests']} | {r['req_per_s']} | {r['output_tok_per_s']} | "
                      f"{r['ttft_p50_s']} | {r['ttft_p95_s']} | {per_user_tok_s(r)} | {usd_per_m(r, usd)} | {'✅' if meets(r) else '❌'} |")
        b = best(lv)
        out["sweeps"][label] = {"levels": lv, "sla_max_users": b["concurrency"] if b else 0,
                                "usd_per_m_at_sla": usd_per_m(b, usd) if b else None,
                                "peak_tok_s": max(r["output_tok_per_s"] for r in lv)}
        md.append(f"\n**SLA capacity: {b['concurrency'] if b else 0} concurrent users, ${usd_per_m(b, usd) if b else 'n/a'} per 1M output tokens at that load.**")

    s = out["sweeps"]
    # E3 vs E2: AMX gain at each matching concurrency
    if "E2-qwen0.6b-amx" in s and "E3-qwen0.6b-noamx" in s:
        on = {r["concurrency"]: r for r in s["E2-qwen0.6b-amx"]["levels"]}
        off = {r["concurrency"]: r for r in s["E3-qwen0.6b-noamx"]["levels"]}
        md += ["", "## AMX on vs off (same model, same 8 cores)", "| users | tok/s AMX on | tok/s AMX off | gain | TTFT p50 on/off |", "|---|---|---|---|---|"]
        gains = []
        for c in sorted(set(on) & set(off)):
            g = on[c]["output_tok_per_s"] / off[c]["output_tok_per_s"] if off[c]["output_tok_per_s"] else None
            gains.append(g)
            md.append(f"| {c} | {on[c]['output_tok_per_s']} | {off[c]['output_tok_per_s']} | {g and round(g, 2)}× | {on[c]['ttft_p50_s']} / {off[c]['ttft_p50_s']} |")
        out["amx_gain_peak"] = round(max(g for g in gains if g), 2) if any(gains) else None
        for n in ("qwen3-0-6b", "qwen3-noamx"):
            f = d / f"onednn-{n}.txt"
            if f.exists(): md += [f"\noneDNN probe `{n}`:", "```", f.read_text().strip()[:600], "```"]

    # E5: routing what-if, from measured peak throughput of each model
    if "E2-qwen0.6b-amx" in s and "E4-qwen2.5-3b-amx" in s:
        small = usd_per_m(max(s["E2-qwen0.6b-amx"]["levels"], key=lambda r: r["output_tok_per_s"]), usd)
        large = usd_per_m(max(s["E4-qwen2.5-3b-amx"]["levels"], key=lambda r: r["output_tok_per_s"]), usd)
        md += ["", "## E5: routing what-if (calculated from measured peak throughput)",
               f"All traffic on 3B: ${large}/1M tokens. All on 0.6B: ${small}/1M tokens.", "| share routed to small model | blended $/1M | saving vs all-3B |", "|---|---|---|"]
        out["routing"] = []
        for share in (0.5, 0.7, 0.9):
            blend = share * small + (1 - share) * large
            out["routing"].append({"small_share": share, "usd_per_m": round(blend, 2), "saving_pct": round(100 * (1 - blend / large))})
            md.append(f"| {int(share*100)}% | ${blend:.2f} | {round(100*(1-blend/large))}% |")
        md.append("\nThis is a calculation, not a measured router. Quality on the routed share has to be checked with an eval set before claiming the saving.")

    (d / "summary.md").write_text("\n".join(md) + "\n"); (d / "summary.json").write_text(json.dumps(out, indent=2))
    print("\n".join(md))


if __name__ == "__main__":
    main()
