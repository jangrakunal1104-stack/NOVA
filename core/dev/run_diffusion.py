#!/usr/bin/env python3

"""
NOVA — Dedicated Diffusion Server (SDXL)
Runs under GPUArbiter control.
"""

import os
import sys
import signal
import time
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models" / "diffusion" / "sdxl" / "base"
OUTPUT_DIR = BASE_DIR / "outputs" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

pipe: StableDiffusionXLPipeline | None = None
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def shutdown_handler(signum, frame):
    global pipe
    print("[SDXL] Shutting down...")
    try:
        if pipe is not None:
            pipe.to("cpu")
            del pipe
            pipe = None
        torch.cuda.empty_cache()
    finally:
        sys.exit(0)


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


def load_pipeline():
    global pipe
    if pipe is not None:
        return pipe

    print(f"[SDXL] Loading from: {MODELS_DIR}")

    pipe = StableDiffusionXLPipeline.from_pretrained(
        str(MODELS_DIR),
        torch_dtype=torch.float16,
        use_safetensors=True,
    )

    pipe.to(DEVICE)

    try:
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()
        pipe.enable_vae_tiling()
    except Exception:
        pass

    return pipe


def generate(prompt: str, width=896, height=896, steps=25, cfg=7.0):
    pipe = load_pipeline()

    print(f"[SDXL] Generating: {prompt}")

    with torch.inference_mode(), torch.autocast("cuda"):
        out = pipe(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
        )

    img = out.images[0]

    ts = int(time.time() * 1000)
    out_path = OUTPUT_DIR / f"sdxl_{ts}.png"
    img.save(out_path)

    print(f"[SDXL] Saved → {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_diffusion.py \"prompt here\"")
        sys.exit(1)

    generate(sys.argv[1])
