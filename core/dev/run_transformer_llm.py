#!/usr/bin/env python3
"""
Transformer LLM backend (GPU-safe, arbiter-friendly)

Design goals:
- Deterministic VRAM usage
- No FlashAttention / xFormers
- No KV cache growth
- Clean coexistence with diffusion + VMs
"""

import os
import threading
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TextIteratorStreamer,
)

# -----------------------------------------------------------------------------
# Environment hardening (MUST be before CUDA init)
# -----------------------------------------------------------------------------

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["XFORMERS_FORCE_DISABLE"] = "1"
os.environ["FLASH_ATTENTION_FORCE_DISABLE"] = "1"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

torch.backends.cuda.enable_flash_sdp(False)
torch.backends.cuda.enable_mem_efficient_sdp(False)
torch.backends.cuda.enable_math_sdp(True)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

MODEL_ID = os.environ.get(
    "TRANSFORMER_MODEL",
    "Qwen/Qwen2.5-3B-Instruct",
)

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8001"))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.bfloat16 if DEVICE == "cuda" else torch.float32

# Leave HARD headroom for diffusion + VMs
GPU_FRACTION = float(os.environ.get("GPU_FRACTION", "0.55"))

# Absolute safety limit
MAX_CONTEXT_LEN = int(os.environ.get("MAX_CONTEXT_LEN", "4096"))

# -----------------------------------------------------------------------------
# FastAPI
# -----------------------------------------------------------------------------

app = FastAPI(title="Transformer LLM Backend")

# -----------------------------------------------------------------------------
# Request schema
# -----------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95

# -----------------------------------------------------------------------------
# Lazy model load (CRITICAL for arbiter)
# -----------------------------------------------------------------------------

tokenizer = None
model = None

def load_model():
    global tokenizer, model

    if model is not None:
        return

    if DEVICE == "cuda":
        torch.cuda.set_per_process_memory_fraction(GPU_FRACTION, device=0)

    print("[LLM] Loading transformer model...")

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        use_fast=True,
    )
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=DTYPE,
        low_cpu_mem_usage=True,
    )

    model.config.use_cache = False
    model.config.pad_token_id = tokenizer.eos_token_id
    model.eval()
    model.to(DEVICE)

    print("[LLM] Model ready")

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend": "transformers",
        "model": MODEL_ID,
        "device": DEVICE,
    }

@app.post("/generate")
def generate(req: GenerateRequest):
    load_model()

    inputs = tokenizer(
        req.prompt,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_CONTEXT_LEN,
    ).to(DEVICE)

    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
    )

    generation_kwargs = dict(
        **inputs,
        streamer=streamer,
        max_new_tokens=req.max_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
        do_sample=True,
        use_cache=False,
    )

    thread = threading.Thread(
        target=model.generate,
        kwargs=generation_kwargs,
        daemon=True,
    )
    thread.start()

    output = ""
    for token in streamer:
        output += token

    thread.join()

    # CRITICAL: release fragmentation
    if DEVICE == "cuda":
        torch.cuda.empty_cache()

    return {"text": output}

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def main():
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

if __name__ == "__main__":
    main()
