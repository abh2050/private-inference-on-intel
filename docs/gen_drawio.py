"""Generates docs/architecture.drawio using draw.io's IBM architecture containers (mxgraph.ibm.box)."""
import sys
from xml.sax.saxutils import escape as _e
escape = lambda s: _e(s, {"\"": "&quot;", "\n": "&#10;"})

cells, n = [], [1]
IBM = ("shape=mxgraph.ibm.box;prType={t};fontStyle=1;verticalAlign=top;align=left;spacingLeft=32;spacingTop=4;"
       "fillColor={f};rounded=0;whiteSpace=wrap;html=1;strokeColor={s};strokeWidth=1;dashed={d};container=1;"
       "spacing=-4;collapsible=0;expand=0;recursiveResize=0;fontSize=12;")
BOXSTYLE = {
    "cloud": dict(s="#4376BB", f="none", d=0), "region": dict(s="#00882B", f="none", d=1),
    "vpc": dict(s="#4376BB", f="none", d=0), "zone": dict(s="#919191", f="none", d=1),
    "subnet": dict(s="#2A8838", f="#E6F0E2", d=0), "public": dict(s="#4376BB", f="none", d=0),
    "enterprise": dict(s="#000000", f="none", d=0),
}


def nid():
    n[0] += 1
    return f"c{n[0]}"


def box(t, label, x, y, w, h, parent="1"):
    i = nid()
    cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{IBM.format(t=t, **BOXSTYLE[t])}" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i


def group(label, x, y, w, h, parent, stroke="#6F6F6F", fill="#FFFFFF", dashed=0, bold=1):
    i = nid()
    st = (f"rounded=0;whiteSpace=wrap;html=1;container=1;collapsible=0;verticalAlign=top;align=left;spacingLeft=8;"
          f"spacingTop=2;fontStyle={bold};fontSize=12;strokeColor={stroke};fillColor={fill};dashed={dashed};")
    cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{st}" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i


def node(label, x, y, w, h, parent, fill="#FFFFFF", stroke="#4376BB", font=11):
    i = nid()
    st = f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fontSize={font};strokeColor={stroke};fillColor={fill};"
    cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{st}" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i


def edge(a, b, label="", color="#161616", dashed=0, width=1.5, extra=""):
    i = nid()
    st = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor={color};"
          f"strokeWidth={width};dashed={dashed};fontSize=11;labelBackgroundColor=#FFFFFF;{extra}")
    cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{st}" edge="1" parent="1" source="{a}" target="{b}">'
                 f'<mxGeometry relative="1" as="geometry"/></mxCell>')


BLUE, GREEN, PURPLE, GREY, YEL = "#D0E2FF", "#DEFBE6", "#E8DAFF", "#F2F4F8", "#FFF8E1"

# Title
cells.append('<mxCell id="title" value="Intel AI for Enterprise Inference on IBM Cloud: single Xeon node with AMX" '
             'style="text;html=1;fontSize=18;fontStyle=1;align=left;verticalAlign=middle;" vertex="1" parent="1">'
             '<mxGeometry x="20" y="10" width="900" height="30" as="geometry"/></mxCell>')

# Operator workstation
op = box("enterprise", "Operator workstation (macOS)", 20, 60, 270, 430)
cli = node("<b>IBM Cloud CLI + scripts</b><br>01-preflight · 02-provision<br>03-run-remote · 99-teardown", 15, 40, 240, 70, op, YEL, "#B28600")
wd = node("<b>Cost watchdog</b><br>deletes every opea-ei-* resource<br>after MAX_HOURS", 15, 125, 240, 60, op, YEL, "#B28600")
an = node("<b>analyze.py</b><br>SLA capacity · $/1M tokens<br>AMX gain · routing what-if", 15, 200, 240, 60, op, YEL, "#B28600")
res = node("<b>results/&lt;run&gt;/</b><br>timeline · friction log · bench JSON<br>pod specs · oneDNN probe", 15, 275, 240, 60, op, GREY, "#6F6F6F")

# Public internet sources
pub = box("public", "Public internet (install-time downloads)", 20, 520, 270, 300)
gh = node("<b>GitHub</b><br>intel/enterprise-ai-solutions v1.1.0<br>→ enterprise-inference v1.0.1", 15, 40, 240, 70, pub, GREY, "#6F6F6F")
dh = node("<b>Container registries</b><br>vllm/vllm-openai-cpu:v0.24.0<br>Kubernetes and platform images", 15, 125, 240, 70, pub, GREY, "#6F6F6F")
hf = node("<b>Hugging Face Hub</b><br>Qwen/Qwen3-0.6B<br>Qwen/Qwen2.5-3B-Instruct", 15, 210, 240, 70, pub, GREY, "#6F6F6F")

# IBM Cloud nesting
cloud = box("cloud", "IBM Cloud", 320, 60, 1340, 1000)
region = box("region", "Region us-east (Washington DC)", 20, 40, 1300, 940, cloud)
vpc = box("vpc", "VPC opea-ei-vpc", 20, 40, 1260, 880, region)
fip = node("<b>Floating IP</b><br>public IPv4", 20, 60, 120, 50, vpc, BLUE)
sg = node("<b>Security group</b><br>inbound: TCP 22 from<br>operator IP only<br>outbound: all", 20, 130, 120, 80, vpc, BLUE)
zone = box("zone", "Zone us-east-1", 160, 30, 1080, 830, vpc)
subnet = box("subnet", "Subnet opea-ei-subnet", 20, 40, 1040, 770, zone)
vsi = group("Virtual server  bx3d-32x160  ·  Intel Xeon (Sapphire Rapids) with AMX  ·  2 sockets × 8 cores (32 vCPU)  ·  160 GB  ·  Ubuntu 24.04  ·  250 GB boot volume",
            15, 40, 1010, 715, subnet, stroke="#0F62FE", fill="#FFFFFF")
bench = node("<b>bench.py</b> (on host)<br>1–16 concurrent streams<br>TTFT · TPOT · tok/s", 15, 40, 170, 70, vsi, YEL, "#B28600")
k8s = group("Kubernetes v1.35 single node (Kubespray)  ·  installed by es_auto_installer.sh", 200, 35, 795, 665, vsi, stroke="#326CE5", fill="#F7FAFF")

# Kubernetes layers
edge_l = group("Edge: TLS and identity", 15, 30, 765, 105, k8s, stroke="#8A3FFC", fill="#FFFFFF", bold=0)
eg = node("<b>Envoy Gateway</b> (eg-gateway)<br>TLS termination · hostname route<br>JWT check (SecurityPolicy)", 10, 28, 245, 65, edge_l, PURPLE, "#8A3FFC")
kc = node("<b>Keycloak</b><br>OIDC realm 'inference'<br>issues bearer tokens", 270, 28, 210, 65, edge_l, PURPLE, "#8A3FFC")
mlb = node("<b>MetalLB</b><br>LoadBalancer IP for<br>the gateway", 495, 28, 255, 65, edge_l, PURPLE, "#8A3FFC")

route_l = group("Routing: pick the model named in the request body", 15, 150, 765, 105, k8s, stroke="#0F62FE", fill="#FFFFFF", bold=0)
aig = node("<b>Envoy AI Gateway</b> (ai-gateway)<br>reads \"model\" from JSON body<br>→ x-ai-eg-model header", 10, 28, 245, 65, route_l, BLUE)
epp = node("<b>EPP scheduler</b><br>endpoint picker for<br>LLMInferenceService", 270, 28, 210, 65, route_l, BLUE)
ks = node("<b>KServe</b> controller<br>LLMInferenceService CRDs<br>model-manager deploys these", 495, 28, 255, 65, route_l, BLUE)

serve_l = group("Serving: one model at a time on the same 8 physical cores", 15, 270, 765, 200, k8s, stroke="#198038", fill="#FFFFFF", bold=0)
vllm = node("<b>vLLM CPU 0.24 pod</b><br>OpenAI-compatible /v1/chat/completions<br>bf16 weights · paged KV cache<br>8 cores pinned to one NUMA node<br>(NRI balloons)", 10, 28, 300, 100, serve_l, GREEN, "#198038")
onednn = node("<b>PyTorch + oneDNN</b><br>bf16 GEMMs", 330, 28, 180, 60, serve_l, GREEN, "#198038")
amx = node("<b>AMX tile unit</b><br>(on every core)<br>E3 caps oneDNN at<br>AVX512_CORE_BF16", 530, 28, 220, 100, serve_l, "#FFD7D9", "#DA1E28")
ovms = node("OpenVINO Model Server (optional runtime, not benchmarked here)", 10, 145, 500, 40, serve_l, GREY, "#8D8D8D", 10)

plat_l = group("Platform services", 15, 485, 765, 165, k8s, stroke="#6F6F6F", fill="#FFFFFF", bold=0)
x = 10
for lbl in ["cert-manager<br>self-signed CA", "Istio", "PostgreSQL<br>(Keycloak DB)", "SeaweedFS<br>object store",
            "Prometheus +<br>Grafana", "local-path storage<br>model weights"]:
    node(lbl, x, 30, 115, 50, plat_l, GREY, "#6F6F6F", 10)
    x += 125
dl = node("<b>model download Job</b><br>pulls weights once, reused on redeploy", 10, 95, 360, 50, plat_l, GREY, "#6F6F6F", 10)
mm = node("<b>model-manager</b> CLI<br>deploy / undeploy · NUMA fit check", 385, 95, 365, 50, plat_l, GREY, "#6F6F6F", 10)

# Intel GPU path (not automated)
gpu = group("Next target: Intel GPU node (Arc Pro B-series / Data Center GPU) with vLLM XPU backend.<br>"
            "Not automated by enterprise-ai-solutions v1.1.0: its docs say Intel GPU support follows a later GPU-enablement milestone.",
            20, 850, 270, 210, "1", stroke="#8D8D8D", fill="#F4F4F4", dashed=1, bold=0)

# Control and data flows
edge(cli, cloud, "① provision / teardown<br>(VPC API)", "#B28600", extra="exitX=1;exitY=0.25;entryX=0;entryY=0.02;")
edge(cli, fip, "② SSH, key only", "#B28600", extra="exitX=1;exitY=0.75;entryX=0;entryY=0.5;")
edge(fip, vsi, "", "#B28600")
edge(gh, vsi, "installer", "#8D8D8D", 1, 1, extra="entryX=0;entryY=0.6;")
edge(dh, vllm, "images", "#8D8D8D", 1, 1)
edge(hf, dl, "weights", "#8D8D8D", 1, 1)
edge(bench, eg, "③ HTTPS + Bearer JWT", "#0F62FE", 0, 2)
edge(eg, kc, "validate token", "#8A3FFC", 1, 1)
edge(eg, aig, "④", "#0F62FE", 0, 2)
edge(aig, epp, "⑤", "#0F62FE", 0, 2)
edge(epp, vllm, "⑥", "#0F62FE", 0, 2, extra="exitX=0.5;exitY=1;entryX=0.8;entryY=0;")
edge(vllm, onednn, "", "#198038")
edge(onednn, amx, "", "#DA1E28")

xml = ('<mxfile host="drawio"><diagram id="arch" name="Architecture"><mxGraphModel dx="1600" dy="1000" grid="1" gridSize="10" '
       'page="1" pageWidth="1700" pageHeight="1100" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
       + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")
open(sys.argv[1], "w").write(xml)
print("wrote", sys.argv[1], len(cells), "cells")
