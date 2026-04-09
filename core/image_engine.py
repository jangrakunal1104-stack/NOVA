#!/usr/bin/env python3

import os, gc, time, base64, subprocess
from typing import Dict, Any, Optional

import torch
from PIL import Image


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DIFFUSION_DIR = os.path.join(MODELS_DIR, "diffusion")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)
SD15_PATH = "/home/panda/ai-stack/NOVA/models/diffusion/sd15"
def image_to_base64(img):
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def create_thumbnail(img, size=256):
    thumb = img.copy()
    w, h = thumb.size
    if w > size:
        new_h = int(h * (size / w))
        thumb = thumb.resize((size, new_h), Image.LANCZOS)
    return thumb
def detect_style(prompt: str) -> str:
    p = prompt.lower()

    if any(x in p for x in ["galaxy", "space", "nebula", "planet", "stars"]):
        return "space"

    if any(x in p for x in ["anime", "manga", "waifu"]):
        return "anime"

    if any(x in p for x in ["portrait", "person", "face", "human"]):
        return "realistic"

    if any(x in p for x in ["painting", "art", "illustration"]):
        return "art"

    return "realistic"


def enhance_prompt(prompt: str) -> str:
    style = detect_style(prompt)

    styles = {
        "realistic": "ultra realistic, cinematic lighting, sharp focus, professional photography",
        "space": "deep space, nasa photography, stars, nebula, cosmic lighting, ultra detailed",
        "anime": "anime style, vibrant colors, clean lines, studio quality, highly detailed",
        "art": "digital painting, concept art, trending on artstation, highly detailed",
    }

    base = styles.get(style, styles["realistic"])

    return f"{prompt}, {base}, high detail, volumetric lighting, 8k"
class ImageEngine:
    def __init__(self):
        self.pipeline = None
        self.model_path = None
        self.device = None

    def unload(self):
        if self.pipeline is not None:
            del self.pipeline
            self.pipeline = None
            gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

    def load_model(self, path: str, device: str):
        from diffusers import StableDiffusionPipeline
        self.unload()

        

        try:
            self.pipeline = StableDiffusionPipeline.from_pretrained(
                path,
                torch_dtype=torch.float16,
                safety_checker=None,
                requires_safety_checker=False,
            )

            

            # MEMORY OPTIMIZATIONS (MANDATORY)
            self.pipeline.enable_attention_slicing()
            self.pipeline.enable_vae_slicing()
            self.pipeline.enable_model_cpu_offload()

            

            self.model_path = path
            self.device = device
            return {"status": "ok"}

        except Exception as e:
            self.unload()
            return {"status": "error", "error": str(e)}

    def generate_image(self, **kw):
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if self.pipeline is None:
            return {"status": "error", "error": "No model loaded"}

        prompt = enhance_prompt(kw["prompt"])
        negative = kw.get(
            "negative_prompt",
            "blurry, low quality, distorted, bad anatomy, artifacts, noise, grainy, deformed"
        )
        
        width = min(int(kw.get("width", 768)), 768)
        height = min(int(kw.get("height", 768)), 768)
        steps = int(kw.get("steps", 35))

        cfg = float(kw.get("cfg", 8.0))

        seed = kw.get("seed")
        gen = None
        if seed is not None:
            gen = torch.Generator(
                device="cuda" if self.device == "gpu" else "cpu"
            ).manual_seed(int(seed))

        result = self.pipeline(
            prompt=prompt,
            negative_prompt=negative,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
            generator=gen,
        )

        return {"status": "ok", "image": result.images[0]}

    def save_outputs(self, img, thumb_size=256):
        ts = int(time.time() * 1000)
        f = os.path.join(OUTPUT_DIR, f"image_{ts}.png")
        t = os.path.join(OUTPUT_DIR, f"image_{ts}_thumb.png")

        img.save(f, "PNG")
        thumb = create_thumbnail(img, thumb_size)
        thumb.save(t, "PNG")

        return {
            "status":"ok",
            "file": f,
            "thumbnail": t,
            "image_b64": image_to_base64(img),
            "thumbnail_b64": image_to_base64(thumb),
        }

    def run_generation(self, payload):
        prompt = payload.get("prompt", "").strip()
        if not prompt:
            return {"status": "error", "error": "Prompt is empty"}

        res = self.generate_image(
            prompt=prompt,
            negative_prompt=payload.get(
                "negative_prompt",
                "blurry, distorted, deformed, bad quality"
            ),
            width=int(payload.get("width", 768)),
            height=int(payload.get("height", 768)),
            steps=int(payload.get("steps", 32)),
            cfg=float(payload.get("cfg", 7.5)),
            seed=payload.get("seed"),
        )

        if res["status"] != "ok":
            return res

        return self.save_outputs(res["image"], int(payload.get("thumb", 256)))


image_engine = ImageEngine()

def diffusion_models():
    models = []
    if os.path.exists(DIFFUSION_DIR):
        for name in os.listdir(DIFFUSION_DIR):
            p = os.path.join(DIFFUSION_DIR,name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p,"model_index.json")):
                models.append({"name":name,"path":p,"type":"sd15"})
    return {"status":"ok","models":models}

def load_diffusion_model(path, device):
    return image_engine.load_model(path, device)

def unload_diffusion_model():
    image_engine.unload()
    return {"status": "ok"}

def generate_diffusion(payload):
    # Auto-load model if not already loaded
    if image_engine.pipeline is None:
        # default SD15 path + gpu
        load_diffusion_model(
            SD15_PATH,
            device="gpu" if torch.cuda.is_available() else "cpu"
        )

    return image_engine.run_generation(payload)

