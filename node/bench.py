#!/usr/bin/env python3
"""End-to-end benchmark through the Enterprise Inference gateway (auth -> AI gateway -> vLLM on Xeon).

Standard library only. Streams each response to measure time to first token (TTFT).
Usage: TOKEN=... python3 bench.py --url https://inference.solutions.ai --model qwen3-0-6b \
         --concurrency 1 4 8 --requests 32 --out ~/results/bench.json
"""
import argparse, json, os, ssl, statistics, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

# A fixed prompt of about 500 tokens, so every run and every machine get the same input.
BASE = ("Intel Xeon processors with Advanced Matrix Extensions accelerate matrix multiplication "
        "for deep learning inference by using dedicated tile registers and a tile matrix unit. ")
PROMPT = (BASE * 22) + "\nSummarize the text above in exactly three bullet points."

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # self-signed certificate created by the installer


def one_request(url, model, token, max_tokens):
    body = json.dumps({
        "model": model, "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": max_tokens, "temperature": 0, "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},  # Qwen3: skip the thinking phase
    }).encode()
    req = urllib.request.Request(url + "/v1/chat/completions", data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    t0 = time.perf_counter(); ttft = None; usage = {}
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=600) as r:
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                chunk = json.loads(line[5:])
                if ttft is None and chunk.get("choices") and chunk["choices"][0].get("delta", {}).get("content"):
                    ttft = time.perf_counter() - t0
                if chunk.get("usage"):
                    usage = chunk["usage"]
    except Exception as e:  # count failures, do not hide them
        return {"ok": False, "error": str(e)[:200]}
    total = time.perf_counter() - t0
    out_toks = usage.get("completion_tokens", 0)
    tpot = (total - ttft) / max(out_toks - 1, 1) if ttft else None
    return {"ok": True, "ttft": ttft, "latency": total, "in_tokens": usage.get("prompt_tokens", 0),
            "out_tokens": out_toks, "tpot": tpot}


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 4) if xs else None


def run_level(args, token, conc):
    one_request(args.url, args.model, token, 8)  # warm-up, not counted
    t0 = time.perf_counter()
    with ThreadPoolExecutor(conc) as ex:
        res = list(ex.map(lambda _: one_request(args.url, args.model, token, args.max_tokens), range(args.requests)))
    wall = time.perf_counter() - t0
    ok = [r for r in res if r["ok"]]
    return {
        "concurrency": conc, "requests": args.requests, "succeeded": len(ok), "failed": len(res) - len(ok),
        "errors": list({r["error"] for r in res if not r["ok"]})[:3],
        "wall_s": round(wall, 2),
        "req_per_s": round(len(ok) / wall, 3),
        "output_tok_per_s": round(sum(r["out_tokens"] for r in ok) / wall, 1),
        "avg_in_tokens": round(statistics.mean(r["in_tokens"] for r in ok), 1) if ok else None,
        "ttft_p50_s": pct([r["ttft"] for r in ok], 50), "ttft_p95_s": pct([r["ttft"] for r in ok], 95),
        "tpot_p50_ms": round(pct([r["tpot"] for r in ok], 50) * 1000, 1) if ok else None,
        "latency_p50_s": pct([r["latency"] for r in ok], 50), "latency_p95_s": pct([r["latency"] for r in ok], 95),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--model", required=True)
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    ap.add_argument("--requests", type=int, default=32); ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--out", default=os.path.expanduser("~/results/bench.json"))
    args = ap.parse_args()
    token = os.environ["TOKEN"]
    results = []
    for c in args.concurrency:
        r = run_level(args, token, c); results.append(r)
        print(json.dumps(r))
    json.dump({"model": args.model, "max_tokens": args.max_tokens, "time": time.strftime("%FT%TZ", time.gmtime()),
               "levels": results}, open(args.out, "w"), indent=2)
    print(f"\n{'conc':>4} {'ok':>4} {'req/s':>7} {'out tok/s':>9} {'TTFT p50':>9} {'TTFT p95':>9} {'TPOT p50 ms':>11}")
    for r in results:
        print(f"{r['concurrency']:>4} {r['succeeded']:>4} {r['req_per_s']:>7} {r['output_tok_per_s']:>9} "
              f"{r['ttft_p50_s']!s:>9} {r['ttft_p95_s']!s:>9} {r['tpot_p50_ms']!s:>11}")


if __name__ == "__main__":
    main()
