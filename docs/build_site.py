#!/usr/bin/env python3
"""Builds docs/index.html (the GitHub Pages results page) from a results run.

Usage: python3 docs/build_site.py results/2026-11-04-run1
Injects run data into docs/template.html. The page draws its charts with D3 (cdnjs, pinned 7.9.0)
and falls back to data tables if D3 does not load.
"""
import csv, json, pathlib, re, sys

RUN = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results/2026-11-04-run1")
HERE = pathlib.Path(__file__).parent
S = json.loads((RUN / "summary.json").read_text())
sw = S["sweeps"]
srt = lambda k: sorted(sw[k]["levels"], key=lambda r: r["concurrency"])
e2, e3, e4 = srt("E2-qwen0.6b-amx"), srt("E3-qwen0.6b-noamx"), srt("E4-qwen2.5-3b-amx")
rate = S["usd_per_hour"]
usd_m = lambda r: rate / (r["output_tok_per_s"] * 3600) * 1e6

rows = list(csv.DictReader((RUN / "timeline.csv").open()))
notes = (RUN / "timeline-notes.txt").read_text()
first_answer = re.search(r"First correct answer at (\d\d:\d\d:\d\d)", notes).group(1)
fr = (RUN / "friction.txt").read_text()
w = re.search(r"prompt from (\d\d:\d\d:\d\d) to (\d\d:\d\d:\d\d)", fr)
sec = lambda t: sum(int(x) * m for x, m in zip(t.split(":"), (3600, 60, 1)))
hms = lambda s: f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
row = {r["phase"]: r for r in rows if not r["phase"].startswith("deploy_")}
first_ok = next(r for r in rows if r["phase"] == "deploy_qwen3-0-6b" and r["exit"] == "0")
idle_s = sec(w.group(2)) - sec(w.group(1))
val_end = sec(row["validate"]["start_utc"]) + int(row["validate"]["seconds"])

timeline = [
    {"label": "OS packages, clone installer", "start": row["os_packages"]["start_utc"], "secs": 8, "kind": "auto"},
    {"label": "configure: waiting at [y/N]", "start": w.group(1), "secs": idle_s, "kind": "idle",
     "note": "No terminal to answer it; --force skips the prompt"},
    {"label": "configure: Python, kubectl, helm", "start": w.group(2), "secs": sec(row["init"]["start_utc"]) - sec(w.group(2)), "kind": "auto"},
    {"label": "install inference (K8s + platform + inference)", "start": row["install_inference"]["start_utc"],
     "secs": int(row["install_inference"]["seconds"]), "kind": "auto", "note": "468 Ansible tasks, 0 failed"},
    {"label": "validate", "start": row["validate"]["start_utc"], "secs": int(row["validate"]["seconds"]), "kind": "auto",
     "note": "Aborted at nfd: validate.yaml missing in v1.1.0"},
    {"label": "manual checks, script fixes", "start": hms(val_end), "secs": sec(first_ok["start_utc"]) - val_end, "kind": "idle",
     "note": "Validated 4 components by hand; worked around the token helper"},
    {"label": "deploy first model", "start": first_ok["start_utc"], "secs": int(first_ok["seconds"]), "kind": "auto",
     "note": "Weight download, pod start, gateway registration"},
    {"label": "smoke test", "start": hms(sec(first_ok["start_utc"]) + int(first_ok["seconds"])),
     "secs": sec(first_answer) - sec(first_ok["start_utc"]) - int(first_ok["seconds"]), "kind": "auto"},
]

FRICTION = [
    {"when": "getting started", "title": "Finding the starting point",
     "what": "The OPEA repository now points to <code>intel/enterprise-inference</code>, which is installed through <code>intel/enterprise-ai-solutions</code>. Reaching the right quick start took a few hops.",
     "fix": "Link every README straight to the one quick start."},
    {"when": "minute 0 – 11", "title": "Unattended installs",
     "what": "<code>configure</code> asks for <code>[y/N]</code> confirmation. In an SSH or CI session nobody answers, so it waits. <code>--force</code> skips the prompt.",
     "fix": "Show <code>--force</code> in the quick start, or name it when no terminal is attached."},
    {"when": "minute 38", "title": "Validation coverage",
     "what": "<code>validate inference</code> stops at <code>nfd</code>, which has no <code>validate.yaml</code> in v1.1.0. The four inference components after it all passed when validated individually.",
     "fix": "Skip components without a validate task and report pass/fail per component."},
    {"when": "minute 40", "title": "Scripting the token helper",
     "what": "<code>get-keycloak-token.sh</code> leaves a RETURN trap set, which stops a calling script that runs with <code>set -u</code>. One line works around it.",
     "fix": "Clear the trap on return, or add a command that prints the token."},
    {"when": "minute 51", "title": "Swapping models back to back",
     "what": "<code>undeploy</code> returns while the pod is still releasing its pinned cores, so an immediate <code>deploy</code> fails NRI pre-flight. Waiting a few seconds resolves it.",
     "fix": "Add <code>undeploy --wait</code>, or let pre-flight wait for terminating pods."},
    {"when": "throughout", "title": "Measuring against an SLA",
     "what": "The stack exposes metrics, but turning them into SLA capacity and cost per token took a separate load generator.",
     "fix": "A <code>model-manager bench</code> that reports against a stated target."},
]

peak = lambda rs: max(rs, key=lambda r: r["output_tok_per_s"])
data = {
    "rate": rate, "sla_ttft": S["sla"]["ttft_p95_s"], "e1": S["e1"], "e2": e2, "e3": e3, "e4": e4,
    "cap_on": sw["E2-qwen0.6b-amx"]["sla_max_users"], "cap_off": sw["E3-qwen0.6b-noamx"]["sla_max_users"],
    "amx_peak": S["amx_gain_peak"], "routing": S["routing"],
    "route_small": round(usd_m(peak(e2)), 2), "route_large": round(usd_m(peak(e4)), 2),
    "timeline": timeline, "first_answer": first_answer, "friction": FRICTION,
}
html = (HERE / "template.html").read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
(HERE / "index.html").write_text(html)
print("wrote", HERE / "index.html", len(html), "bytes")
