#!/usr/bin/env python3
"""Queue O'AILLY circuit-insect cover illustrations on ComfyUI (Flux.1-dev fp8)."""
import json, sys, time, urllib.request

HOST = "http://127.0.0.1:8388"

STYLE = ("A {creature} illustrated as electronic circuitry, technical schematic art. "
         "Top-down view, perfectly bilaterally symmetrical, centered. Medium-weight "
         "{color} line art on a flat near-black charcoal background. The {creature}'s "
         "thorax is a rectangular integrated circuit chip package with pin legs; its "
         "anatomy is built from PCB traces that run parallel and bend at 45 and 90 "
         "degree angles, ending in small round vias and circular solder pads. {extra} "
         "Behind the {creature}, a faint thin rectangular circuit-board outline with "
         "four corner mounting holes, like a PCB silkscreen. Clean sparse flat vector "
         "aesthetic, engineering schematic style, high contrast linework, no gradients, "
         "no glow, no text, no labels, no watermark.")

VARIANTS = {
    "beetle":    {"color": "warm copper-orange",
                  "extra": "Broad armored elytra outlined as two large rounded copper zones split by a straight center seam stitched with vias; six segmented angular legs like bent pin headers; two antennae ending in round terminal pads."},
    "dragonfly": {"color": "bright teal-cyan",
                  "extra": "Two pairs of long slender wings whose venation is a dense grid of circuit traces with vias at every junction; a long thin abdomen drawn as a vertical pin header strip; two large round eyes as concentric solder pads."},
    "moth":      {"color": "light lavender purple",
                  "extra": "Broad swept triangular forewings whose veins are radiating circuit traces with via dots; one concentric-circle chip footprint pad on each forewing; feathered comb antennae drawn as parallel trace combs."},
    "caterpillar": {"color": "muted sage-green",
                  "extra": "A plump segmented larva shown top-down as a vertical stack of about eight identical rounded-rectangular IC-package body segments joined by short ribbon-cable traces, each segment edged with a pair of small round vias; many short stubby prolegs drawn as bent pin-header stubs along both sides; a rounded head module at the top with two round solder-pad eyes and two very short antennae ending in vias."},
    "termite":   {"color": "warm amber-gold",
                  "extra": "A pale worker termite top-down: a rounded head module at the top with two strong forward mandibles drawn as angular caliper traces, a rectangular integrated-circuit thorax, and a long abdomen built from a vertical stack of rounded-rectangular chip modules; six segmented legs like bent pin headers; the linework pale and even so it reads as a blind builder."},
}
import os
_ONLY = {c.strip() for c in os.environ.get("OAILLY_CREATURES", "").split(",") if c.strip()}

def graph(prompt, seed, prefix):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "FluxGuidance",
              "inputs": {"guidance": 3.5, "conditioning": ["2", 0]}},
        "5": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": 24, "cfg": 1.0,
                         "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0, "model": ["1", 0],
                         "positive": ["4", 0], "negative": ["3", 0],
                         "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
    }

def post(path, data):
    req = urllib.request.Request(HOST + path, json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def get(path):
    return json.load(urllib.request.urlopen(HOST + path, timeout=30))

seeds = [int(s) for s in (sys.argv[1:] or ["20260827", "8827001"])]
jobs = {}
for name, v in VARIANTS.items():
    if _ONLY and name not in _ONLY:
        continue
    for seed in seeds:
        p = STYLE.format(creature=name, **v)
        r = post("/prompt", {"prompt": graph(p, seed, f"oailly/{name}-s{seed}")})
        jobs[r["prompt_id"]] = f"{name}-s{seed}"
        print("queued", jobs[r["prompt_id"]])

t0 = time.time()
pending = set(jobs)
while pending and time.time() - t0 < 900:
    time.sleep(6)
    hist = get("/history")
    for pid in list(pending):
        if pid in hist and hist[pid].get("status", {}).get("completed"):
            outs = [f"{o['subfolder']}/{o['filename']}"
                    for node in hist[pid]["outputs"].values()
                    for o in node.get("images", [])]
            print(f"done {jobs[pid]}: {outs}")
            pending.discard(pid)
        elif pid in hist and hist[pid].get("status", {}).get("status_str") == "error":
            print(f"ERROR {jobs[pid]}")
            pending.discard(pid)
print("all done" if not pending else f"TIMEOUT waiting for {len(pending)}")
