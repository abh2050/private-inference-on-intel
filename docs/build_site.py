#!/usr/bin/env python3
"""Builds docs/index.html (the GitHub Pages results page) from a results run.

Usage: python3 docs/build_site.py results/20261103-2026
Reads summary.json and timeline.csv written by analyze.py and the run; no network, no external libraries.
"""
import csv, html, json, math, pathlib, sys

RUN = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results/20261103-2026")
OUT = pathlib.Path(__file__).parent / "index.html"
S = json.loads((RUN / "summary.json").read_text())
USD_H = S["usd_per_hour"]
SLA_TTFT = S["sla"]["ttft_p95_s"]

sw = S["sweeps"]
e2 = sorted(sw["E2-qwen0.6b-amx"]["levels"], key=lambda r: r["concurrency"])
e3 = sorted(sw["E3-qwen0.6b-noamx"]["levels"], key=lambda r: r["concurrency"])
e4 = sorted(sw["E4-qwen2.5-3b-amx"]["levels"], key=lambda r: r["concurrency"])
SERIES = [  # (key, label, css var, rows)
    ("on", "Qwen3-0.6B, AMX on", "--s1", e2),
    ("off", "Qwen3-0.6B, AMX off", "--s2", e3),
    ("3b", "Qwen2.5-3B, AMX on", "--s3", e4),
]
per_user = lambda r: round(1000 / r["tpot_p50_ms"], 1) if r.get("tpot_p50_ms") else 0
usd_m = lambda r: round(USD_H / (r["output_tok_per_s"] * 3600) * 1e6, 2) if r["output_tok_per_s"] else None
e1 = S["e1"]
cap_on, cap_off = sw["E2-qwen0.6b-amx"]["sla_max_users"], sw["E3-qwen0.6b-noamx"]["sla_max_users"]
usd_on, usd_off = sw["E2-qwen0.6b-amx"]["usd_per_m_at_sla"], sw["E3-qwen0.6b-noamx"]["usd_per_m_at_sla"]
amx_peak = S["amx_gain_peak"]
routing70 = next(r for r in S["routing"] if r["small_share"] == 0.7)

# ---------- chart: line chart, log2 x (users), linear y ----------
W, H, PL, PR, PT, PB = 640, 300, 56, 132, 16, 40
XT = [1, 2, 4, 8, 16, 32, 48]


def xpos(c):
    return PL + (math.log2(c) - 0) / (math.log2(48) - 0) * (W - PL - PR)


def line_chart(cid, field, ymax, yticks, yfmt, title_unit, threshold=None):
    ypos = lambda v: PT + (1 - v / ymax) * (H - PT - PB)
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="{cid}-t" class="chart" id="{cid}">']
    for t in yticks:  # recessive grid
        y = ypos(t)
        g.append(f'<line x1="{PL}" x2="{W-PR}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                 f'<text x="{PL-8}" y="{y+4:.1f}" class="tick" text-anchor="end">{yfmt(t)}</text>')
    for c in XT:
        g.append(f'<text x="{xpos(c):.1f}" y="{H-PB+18}" class="tick" text-anchor="middle">{c}</text>')
    g.append(f'<text x="{(PL+W-PR)/2:.0f}" y="{H-4}" class="axis-title" text-anchor="middle">concurrent users (log scale)</text>')
    if threshold is not None:
        y = ypos(threshold)
        g.append(f'<line x1="{PL}" x2="{W-PR}" y1="{y:.1f}" y2="{y:.1f}" class="threshold"/>'
                 f'<text x="{W-PR+6}" y="{y+4:.1f}" class="thr-label">target {threshold:g} s</text>')
    for key, label, var, rows in SERIES:
        pts = [(xpos(r["concurrency"]), ypos(min(r[field], ymax))) for r in rows]
        d = " ".join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}' for i, (x, y) in enumerate(pts))
        g.append(f'<path d="{d}" class="series" style="stroke:var({var})"/>')
        for r, (x, y) in zip(rows, pts):
            tip = (f'{label} · {r["concurrency"]} users|{field.replace("_", " ")}: {yfmt(r[field])}'
                   f'|output: {r["output_tok_per_s"]} tok/s · TTFT p95 {r["ttft_p95_s"]} s')
            g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="dot" style="fill:var({var})"/>'
                     f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" class="hit" data-tip="{html.escape(tip)}"/>')
        lx, ly = pts[-1]
        g.append(f'<text x="{lx+10:.1f}" y="{ly+4:.1f}" class="direct">{html.escape(label.split(", ")[-1] if key != "3b" else "3B model")}</text>')
    g.append("</svg>")
    return "".join(g)


thr_chart = line_chart("c-tput", "output_tok_per_s", 240, [0, 60, 120, 180, 240], lambda v: f"{v:g}", "tok/s")
ttft_chart = line_chart("c-ttft", "ttft_p95_s", 9, [0, 2, 4, 6, 8], lambda v: f"{v:g} s", "s", threshold=SLA_TTFT)

# ---------- chart: E1 phase bars ----------
rows = list(csv.DictReader((RUN / "timeline.csv").open()))
first_ok = next(r for r in rows if r["phase"] == "deploy_qwen3-0-6b" and r["exit"] == "0")
phases = [
    ("Install OS packages, clone installer", 8, "auto"),
    ("configure: prompt waiting for [y/N]", round(e1["idle_prompt_min"] * 60), "idle"),
    ("configure: Python, kubectl, helm", 758 - round(e1["idle_prompt_min"] * 60), "auto"),
    ("install inference: Kubernetes + platform + inference", int(next(r for r in rows if r["phase"] == "install_inference")["seconds"]), "auto"),
    ("validate (aborts at nfd), manual checks, script fixes", 37 + 191 + 64, "idle"),
    ("Deploy first model (download, start, register)", int(first_ok["seconds"]), "auto"),
]
BW, BH = 640, 26 * len(phases) + 30
maxs = max(p[1] for p in phases)
bars = [f'<svg viewBox="0 0 {BW} {BH}" class="chart" role="img" aria-label="Time per deployment phase">']
for i, (name, secs, kind) in enumerate(phases):
    y = 8 + i * 26
    w = max(3, secs / maxs * (BW - 330))
    bars.append(f'<text x="0" y="{y+14}" class="tick">{html.escape(name)}</text>'
                f'<rect x="300" y="{y+2}" width="{w:.1f}" height="16" rx="4" class="bar-{kind}" data-tip="{html.escape(name)}|{secs/60:.1f} min"/>'
                f'<text x="{300+w+6:.1f}" y="{y+14}" class="val">{secs/60:.1f} min</text>')
bars.append("</svg>")
e1_chart = "".join(bars)


# ---------- tables ----------
def table(rows, cols):
    head = "".join(f"<th>{h}</th>" for h, _ in cols)
    body = "".join("<tr>" + "".join(f"<td>{f(r)}</td>" for _, f in cols) + "</tr>" for r in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


sweep_cols = [("Users", lambda r: r["concurrency"]), ("Succeeded", lambda r: f'{r["succeeded"]}/{r["requests"]}'),
              ("Output tok/s", lambda r: r["output_tok_per_s"]), ("TTFT p50", lambda r: f'{r["ttft_p50_s"]} s'),
              ("TTFT p95", lambda r: f'{r["ttft_p95_s"]} s'), ("Tok/s per user", per_user),
              ("$ / 1M tokens", lambda r: f"${usd_m(r)}"),
              ("Target", lambda r: "✓ met" if (r["failed"] == 0 and r["ttft_p95_s"] <= SLA_TTFT and per_user(r) >= 10) else "✗ missed")]
tables = "".join(f"<h4>{lbl}</h4>{table(rows, sweep_cols)}" for _, lbl, _, rows in SERIES)

FRICTION = [
    ("Three repositories, one entry point unclear",
     "The OPEA repo is archived with a “moved” notice; the new inference repo is not installable alone and is driven by a third repo.",
     "Point every README at one quick start in enterprise-ai-solutions."),
    ("configure stops at an interactive [y/N] prompt",
     "Over SSH or CI it waits forever (11.4 min here). <code>--force</code> skips it, but the quick start does not mention it.",
     "Document <code>--force</code> in the quick start, or detect a non-terminal and say which flag to pass."),
    ("validate fails on a healthy cluster",
     "It aborts at <code>nfd</code>, whose <code>validate.yaml</code> is missing in v1.1.0, so the inference components after it are never checked.",
     "Skip components without a validate task, and report pass/fail per component instead of aborting."),
    ("Token helper breaks strict-mode scripts",
     "<code>get-keycloak-token.sh</code> leaves a RETURN trap that aborts callers running <code>set -u</code>.",
     "Clear the trap, or offer a non-sourced command that prints the token."),
    ("undeploy returns before cores are free",
     "A deploy issued straight after an undeploy failed NRI pre-flight (“not enough physical cores”) on an empty node.",
     "Add <code>undeploy --wait</code>, or have pre-flight wait for terminating pods."),
    ("No built-in SLA benchmark",
     "TTFT, tokens/s per user, and cost per token had to be measured with a separate load generator.",
     "Ship a <code>model-manager bench</code> that reports these against a stated target."),
]
friction_rows = "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td></tr>" for a, b, c in FRICTION)

page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Private LLM Inference on Intel Xeon</title>
<meta name="description" content="Measured deployment effort, SLA capacity, cost per token, and AMX contribution for Intel AI for Enterprise Inference on an IBM Cloud Xeon server.">
<style>
:root{{color-scheme:light;--bg:#fcfcfb;--card:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--ink3:#7a7974;--line:#e4e3df;--grid:#ecebe7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--idle:#b9b7b0;--accent:#2a78d6;--warn:#b54708}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme="light"])){{color-scheme:dark;--bg:#141413;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8f8e87;--line:#2e2d2a;--grid:#262624;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--idle:#55544f;--accent:#5598e7;--warn:#f79009}}}}
:root[data-theme="dark"]{{color-scheme:dark;--bg:#141413;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8f8e87;--line:#2e2d2a;--grid:#262624;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--idle:#55544f;--accent:#5598e7;--warn:#f79009}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:40px 16px 80px}}
h1{{font-size:34px;line-height:1.15;margin:0 0 12px;letter-spacing:-.01em}}
h2{{font-size:22px;margin:56px 0 8px}} h3{{font-size:17px;margin:28px 0 6px}} h4{{font-size:14px;margin:20px 0 6px;color:var(--ink2)}}
p,li{{color:var(--ink2)}} p.lead{{font-size:18px;color:var(--ink2);max-width:760px}}
a{{color:var(--accent)}} code{{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--grid);padding:1px 5px;border-radius:4px}}
.meta{{font-size:14px;color:var(--ink3);margin-top:8px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:28px 0 8px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}}
.tile .n{{font-size:30px;font-weight:650;letter-spacing:-.01em;color:var(--ink)}} .tile .l{{font-size:14px;color:var(--ink2);margin-top:4px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px;margin:16px 0}}
.chart{{width:100%;height:auto;display:block;overflow:visible}}
.grid{{stroke:var(--grid);stroke-width:1}} .tick{{fill:var(--ink3);font-size:12px}} .axis-title{{fill:var(--ink3);font-size:12px}}
.series{{fill:none;stroke-width:2;stroke-linejoin:round}} .dot{{stroke:var(--card);stroke-width:2}}
.hit{{fill:transparent;cursor:crosshair}} .direct{{fill:var(--ink2);font-size:12px;font-weight:600}} .val{{fill:var(--ink2);font-size:12px}}
.threshold{{stroke:var(--ink3);stroke-width:1.5;stroke-dasharray:5 4}} .thr-label{{fill:var(--ink3);font-size:12px}}
.bar-auto{{fill:var(--s1)}} .bar-idle{{fill:var(--idle)}}
.legend{{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--ink2);margin:4px 0 10px}}
.legend span::before{{content:"";display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle;background:var(--c)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} @media (max-width:760px){{.two{{grid-template-columns:1fr}}}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:6px 0 12px}} th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--ink3);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}} td{{color:var(--ink2)}}
.scroll{{overflow-x:auto}}
details{{margin-top:8px}} summary{{cursor:pointer;color:var(--accent);font-size:14px}}
figure{{margin:16px 0}} figure img{{width:100%;border:1px solid var(--line);border-radius:10px;background:#fff}} figcaption{{font-size:13px;color:var(--ink3);margin-top:6px}}
.note{{font-size:14px;color:var(--ink3)}}
pre{{overflow-x:auto;background:var(--grid);padding:12px;border-radius:8px}} pre code{{background:none;padding:0}} code{{overflow-wrap:anywhere}}
@media (max-width:600px){{h1{{font-size:26px}} p.lead{{font-size:16px}} .toggle{{position:static;margin:12px 16px 0}}}}
#tip{{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);font-size:12px;padding:6px 8px;border-radius:6px;opacity:0;transition:opacity .1s;max-width:280px;z-index:9}}
.toggle{{position:absolute;top:16px;right:16px;background:var(--card);color:var(--ink2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;cursor:pointer}}
</style></head>
<body>
<button class="toggle" id="theme" aria-label="Toggle dark mode">Theme</button>
<div id="tip" role="tooltip"></div>
<main>
<h1>Private LLM inference on Intel Xeon: how hard is it, and what do you get?</h1>
<p class="lead">I installed Intel AI for Enterprise Inference on one IBM Cloud Xeon server, served open models through its OpenAI-compatible gateway, and measured the effort to deploy it, the users one node serves within a latency target, the cost per token, and what Intel AMX contributes.</p>
<p class="meta">Run 1 · 2026-11-04 · IBM Cloud <code>bx3d-32x160</code> (4th Gen Xeon, AMX) · enterprise-ai-solutions v1.1.0 / enterprise-inference v1.0.1 · vLLM CPU 0.24 ·
<a href="https://github.com/abh2050/private-inference-on-intel">Repository and raw data</a></p>

<div class="tiles">
 <div class="tile"><div class="n">{e1['automation_min']} min</div><div class="l">bare server to first correct answer, automation time ({e1['wall_clock_min']} min wall clock)</div></div>
 <div class="tile"><div class="n">{cap_on} users</div><div class="l">served by 8 Xeon cores within the latency target</div></div>
 <div class="tile"><div class="n">${usd_on:.2f}</div><div class="l">per 1M output tokens at that load*</div></div>
 <div class="tile"><div class="n">{cap_on} vs {cap_off}</div><div class="l">users within target with AMX vs without; up to {amx_peak}× throughput</div></div>
</div>
<p class="note">*At an estimated ${USD_H:.2f} per server-hour (IBM's partial billing data so far implies about $2). Ratios between configurations do not depend on the rate.</p>

<h2>The problem</h2>
<p>Teams that move LLM inference onto their own infrastructure, for cost, data privacy, or air-gap reasons, have to answer four questions before they commit hardware. Vendor documentation answers none of them with numbers:</p>
<ol>
<li><b>Effort:</b> how long from an empty machine to an authenticated, OpenAI-compatible endpoint, and where does it break?</li>
<li><b>Capacity:</b> how many concurrent users does one node serve before latency becomes unacceptable?</li>
<li><b>Economics:</b> what does a million output tokens cost at that load?</li>
<li><b>Hardware value:</b> how much of the CPU result comes from Intel AMX?</li>
</ol>
<p>The latency target was fixed before the run: p95 time to first token (TTFT) of at most {SLA_TTFT:g} s, at least 10 output tokens/s per user, and no failed requests.</p>

<h2>What was deployed</h2>
<figure><img src="architecture.png" alt="IBM Cloud VPC with one Xeon server running single-node Kubernetes. Requests pass through Envoy Gateway with Keycloak JWT check, Envoy AI Gateway, an EPP scheduler, and a vLLM CPU pod pinned to 8 cores whose bf16 matrix math runs on AMX via oneDNN.">
<figcaption>Request path: client → Envoy Gateway (TLS, Keycloak JWT) → Envoy AI Gateway (reads <code>model</code> from the body) → EPP scheduler → vLLM on 8 NUMA-pinned cores → oneDNN → AMX. <a href="architecture.png">Full size</a> · <a href="architecture.drawio">draw.io source</a></figcaption></figure>

<h2>Capacity and latency</h2>
<p>Same 8 physical cores (one NUMA node) for every model, a ~600-token prompt, 128 output tokens, all traffic through the authenticated gateway. Every request succeeded at every load level.</p>
<div class="legend"><span style="--c:var(--s1)">Qwen3-0.6B, AMX on</span><span style="--c:var(--s2)">Qwen3-0.6B, AMX off</span><span style="--c:var(--s3)">Qwen2.5-3B, AMX on</span></div>
<div class="two">
 <div class="card"><h3 style="margin-top:0">Output throughput (tokens/s)</h3>{thr_chart}</div>
 <div class="card"><h3 style="margin-top:0">Time to first token, p95</h3>{ttft_chart}</div>
</div>
<ul>
<li><b>AMX on:</b> throughput rises to about 217 tokens/s and levels off near 30 users. The target holds through <b>{cap_on} users</b> and fails at 32, when TTFT p95 passes {SLA_TTFT:g} s.</li>
<li><b>AMX off</b> (same cores, oneDNN capped at AVX-512 BF16): throughput stalls near 59 tokens/s and TTFT reaches 8.4 s at 16 users. The target holds for only <b>{cap_off} users</b>.</li>
<li><b>3B model:</b> answers correctly but gives one user 5.2 tokens/s, below the 10 required at any load. On 8 cores it needs more cores per replica.</li>
</ul>
<details><summary>Data tables</summary><div class="scroll">{tables}</div></details>

<h2>What AMX contributes</h2>
<p>With one user, AMX adds 1.2×, because decode is limited by memory bandwidth. Under load it adds up to <b>{amx_peak}×</b>, because prompt processing (prefill) is compute-bound and AMX is a matrix unit. At the target, that is {cap_on} users at ${usd_on:.2f} per million tokens with AMX against {cap_off} users at ${usd_off:.2f} without it, on the same hardware.</p>
<div class="card"><p style="margin-top:0">oneDNN reports the kernel each pod actually ran:</p>
<p><code>AMX on → brg_matmul:avx10_1_512_amx</code><br><code>AMX off → brg_matmul:avx512_core_bf16</code></p></div>

<h2>Deployment effort</h2>
<p>The install itself was solid: 468 Ansible tasks, none failed, and 49 pods healthy with 0 restarts. The time went to the steps around it. Gray bars are waiting or manual work; blue bars are automation.</p>
<div class="card">{e1_chart}</div>
<p>Wall clock {e1['wall_clock_min']} min; automation {e1['automation_min']} min; three manual interventions before the first correct answer.</p>

<h3>Friction found, and the fix for each</h3>
<div class="scroll"><table><thead><tr><th>Issue</th><th>What happened</th><th>Suggested fix</th></tr></thead><tbody>{friction_rows}</tbody></table></div>
<p class="note">The current release automates Xeon serving and NVIDIA GPU nodes. Its docs place Intel GPU support in a later milestone, and Gaudi support exists only in the archived OPEA version. IBM Cloud offers Intel Gaudi 3 but no Intel Arc or Data Center GPU instances. This run covers Xeon only.</p>

<h2>Routing: a calculated saving</h2>
<p>From the measured peak throughputs, sending 70% of requests to the 0.6B model and 30% to the 3B model would cost <b>${routing70['usd_per_m']}</b> per million tokens against ${usd_m(max(e4, key=lambda r: r['output_tok_per_s']))} for all-3B, a <b>{routing70['saving_pct']}%</b> saving. This is arithmetic, not a measured router. An evaluation set would have to show the small model answers that share of real traffic acceptably first.</p>

<h2>Limits</h2>
<ul>
<li>One server and one run per configuration, so run-to-run variance is not yet measured.</li>
<li>The load generator ran on the same server. The model's cores were pinned; the client's were not.</li>
<li>Costs use an estimated hourly rate. Rerun <code>analyze.py</code> with the invoiced rate.</li>
</ul>

<h2>Reproduce</h2>
<p>About two hours of server time, roughly $3. Every step, log, and benchmark file from this run is in the <a href="https://github.com/abh2050/private-inference-on-intel">repository</a>, along with a per-minute <a href="https://github.com/abh2050/private-inference-on-intel/blob/main/logs/operator-log.md">operator log</a>.</p>
<pre><code>ibmcloud login --sso
./01-preflight.sh
CONFIRM=yes ./02-provision.sh
./03-run-remote.sh &amp;&amp; ./03-run-remote.sh collect
python3 analyze.py results/&lt;run&gt; --usd-per-hour &lt;rate&gt;
CONFIRM=yes ./99-teardown.sh</code></pre>
</main>
<script>
(function(){{
 var tip=document.getElementById('tip');
 document.querySelectorAll('[data-tip]').forEach(function(el){{
  el.addEventListener('mousemove',function(e){{var p=el.getAttribute('data-tip').split('|');tip.innerHTML='<b>'+p[0]+'</b><br>'+p.slice(1).join('<br>');
   tip.style.left=Math.min(e.clientX+14,window.innerWidth-290)+'px';tip.style.top=(e.clientY+14)+'px';tip.style.opacity=1;}});
  el.addEventListener('mouseleave',function(){{tip.style.opacity=0;}});
 }});
 var r=document.documentElement,b=document.getElementById('theme');
 try{{var s=localStorage.getItem('theme');if(s)r.setAttribute('data-theme',s);}}catch(e){{}}
 b.addEventListener('click',function(){{var dark=r.getAttribute('data-theme')==='dark'||(!r.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);
  var n=dark?'light':'dark';r.setAttribute('data-theme',n);try{{localStorage.setItem('theme',n);}}catch(e){{}}}});
}})();
</script>
</body></html>
"""
OUT.write_text(page)
print("wrote", OUT, len(page), "bytes")
