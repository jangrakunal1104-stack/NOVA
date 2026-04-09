#!/usr/bin/env python3
# NOVA — Universal Model Loader (STABLE FIXED VERSION)
# Supports: GGUF (llama.cpp), Transformers, ONNX
# vLLM intentionally excluded

from importlib.resources import path
import os
import threading
import subprocess
from typing import Dict, Any, Generator, Optional, List
home = os.path.expanduser("~")
#----------------------------
# Optional deps
# ----------------------------
try:
    import torch
except Exception:
    torch = None

try:
    from llama_cpp import Llama
except Exception:
    Llama = None

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
except Exception:
    AutoModelForCausalLM = None
    AutoTokenizer = None
    TextIteratorStreamer = None

try:
    import onnxruntime as ort
except Exception:
    ort = None


# ======================================================
# GPU VRAM detection
# ======================================================
def clean_llm_output(text: str) -> str:
    BAD_TOKENS = (
        "[INST]", "[/INST]",
        "<jupyter_code>", "</jupyter_code>",
        "<jupyter_text>", "</jupyter_text>",
        "[WRAP]", "[/WRAP]", "[WRAP-python]"
    )
    for t in BAD_TOKENS:
        text = text.replace(t, "")
    return text

def get_gpu_vram() -> Dict[str, float]:
    if torch and torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        total = props.total_memory / 1024**3
        free = total - (torch.cuda.memory_allocated(0) / 1024**3)
        return {"total": round(total, 2), "free": round(free, 2)}

    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ]
        ).decode()
        total_mb, free_mb = map(float, out.split(","))
        return {"total": round(total_mb / 1024, 2), "free": round(free_mb / 1024, 2)}
    except Exception:
        return {"total": 0.0, "free": 0.0}


# ======================================================
# Model Loader
# ======================================================
class ModelLoader:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.backend: Optional[str] = None
        self.device = "cpu"
        self.model_path: Optional[str] = None
        self.ctx_size = 4096
        self.models = {
            "chat": f"{home}/ai-stack/NOVA/models/gguf/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
            "code": f"{home}/ai-stack/NOVA/models/gguf/qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        }


    # --------------------------------------------------
    def is_model_loaded(self) -> bool:
        return self.model is not None

    def detect_backend(self, path: str) -> str:
        if path.endswith(".gguf"):
            return "gguf"
        if path.endswith(".onnx"):
            return "onnx"
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "config.json")):
            return "transformers"
        return "unknown"

    # --------------------------------------------------
    def get_loaded_model_name(self) -> Optional[str]:
        if not self.model_path:
            return None
        return os.path.basename(self.model_path)

    def load(self, path: str, device: str = "cpu", force_backend: Optional[str] = None):
        return self.load_model(
            path=path,
            device=device,
            force_backend=force_backend,
        )

    def get_model_info(self):
        if not self.model:
            return None

        name = None
        if self.model_path:
            name = os.path.basename(self.model_path)
            if name.endswith(".gguf"):
                name = name.replace(".gguf", "")

        return {
            "name": name,
            "backend": self.backend,
            "device": self.device,
            "path": self.model_path,
        }
    def set_ctx_size(self, ctx_size: int):
        self.ctx_size = int(ctx_size)

    def unload_model(self):
        import gc
        print("[MODEL LOADER] Unloading model...")

        try:
            if self.model is not None:
                # GGUF (llama.cpp)
                if hasattr(self.model, "close"):
                    try:
                        self.model.close()
                    except:
                        pass

                del self.model

            if self.tokenizer is not None:
                del self.tokenizer

        except Exception as e:
            print(f"[MODEL LOADER] Unload error: {e}")

        self.model = None
        self.tokenizer = None
        self.backend = None
        self.model_path = None
        self.device = "cpu"

        gc.collect()

        if torch and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            torch.cuda.synchronize()

    # --------------------------------------------------
    def load_model(
            self,
            path: str,
            device: str = "cpu",
            force_backend: Optional[str] = None,
    ) -> Dict[str, Any]:

        if self.model_path != path:
            self.unload_model()

        backend = force_backend or self.detect_backend(path)
        self.backend = backend
        self.device = device
        self.model_path = path

        try:
            if backend == "gguf":
                return self._load_gguf(path)

            if backend == "transformers":
                return self._load_transformers(path, device)

            if backend == "onnx":
                return self._load_onnx(path)
            
            if backend == "unknown":
                return {"status": "error", "error": f"Invalid model path: {path}"}

            return {"status": "error", "error": f"Unsupported backend: {backend}"}

        except Exception as e:
            self.unload_model()
            return {"status": "error", "error": str(e)}

    # ==================================================
    # GGUF (llama.cpp)
    # ==================================================
    def _load_gguf(self, path: str) -> Dict[str, Any]:
        if not Llama:
            return {"status": "error", "error": "llama.cpp not installed"}

        self.model = Llama(
            model_path=path,
            n_ctx=4096,

            # CPU
            n_threads=os.cpu_count(),

            # 🔥 PERFORMANCE (CRITICAL)
            n_batch=512,

            # 🔥 GPU UTILIZATION (RTX 3060)
            n_gpu_layers=40 if torch and torch.cuda.is_available() else 0,

            # 🔥 MEMORY + SPEED
            offload_kqv=True,
            use_mlock=True,
        )

        return {"status": "ok", "backend": "gguf"}

    # ==================================================
    # Transformers
    # ==================================================
    def _load_transformers(self, path: str, device: str) -> Dict[str, Any]:
        if torch is None:
            return {"status": "error", "error": "torch not available"}

        if not AutoModelForCausalLM:
            return {"status": "error", "error": "transformers not installed"}

        self.tokenizer = AutoTokenizer.from_pretrained(
            path,
            trust_remote_code=True,
            local_files_only=True,
        )

        use_gpu = device == "gpu" and torch and torch.cuda.is_available()
        dtype = torch.float16 if use_gpu else torch.float32
        device_map = "auto" if use_gpu else None

        self.model = AutoModelForCausalLM.from_pretrained(
            path,
            torch_dtype=dtype,
            device_map=device_map,
            trust_remote_code=True,
            local_files_only=True,
        )

        self.model.eval()

        return {"status": "ok", "backend": "transformers"}

    # ==================================================
    # ONNX
    # ==================================================
    def _load_onnx(self, path: str) -> Dict[str, Any]:
        if not ort:
            return {"status": "error", "error": "onnxruntime not installed"}

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] \
            if ort.get_device() == "GPU" else ["CPUExecutionProvider"]

        self.model = ort.InferenceSession(path, providers=providers)
        return {"status": "ok", "backend": "onnx"}

    # ==================================================
    # Streaming interface
    # ==================================================
    def generate_stream(self, messages):
        try:
            if self.backend == "gguf":
                yield from self._stream_gguf(messages)

            elif self.backend == "transformers":
                yield from self._stream_transformers(messages)

            else:
                raise RuntimeError(
                    f"Unsupported backend: {self.backend}"
                )

        except Exception as e:
            # 🔥 NEVER crash silently
            yield f"\n[ERROR] {str(e)}\n"

    # --------------------------------------------------
    def _stream_gguf(self, messages):
        if self.model is None:
            raise RuntimeError("GGUF model not loaded")

        self.model.reset()

        # ----------------------------
        # Build prompt
        # ----------------------------
        prompt = ""

        for m in messages:
            role = m.get("role")
            content = m.get("content", "").strip()

            if not content:
                continue

            if role == "system":
                prompt += f"{content}\n\n"
            elif role == "user":
                prompt += f"[INST] {content} [/INST]\n"
            elif role == "assistant":
                prompt += f"{content}\n"

        prompt += "Assistant: "

        # ----------------------------
        # Stream tokens
        # ----------------------------
        try:
            for chunk in self.model(
                    prompt,
                    max_tokens=1024,
                    temperature=0.6,
                    top_p=0.9,
                    top_k=40,
                    repeat_penalty=1.1,
                    presence_penalty=0.2,
                    frequency_penalty=0.1,
                    stream=True,
                    stop=["User:"],  # ← DO NOT stop on "Assistant:"
            ):
                if not chunk:
                    continue

                choices = chunk.get("choices")
                if not choices:
                    continue

                delta = choices[0].get("text")
                if not delta:
                    continue

                yield clean_llm_output(delta)

        except Exception as e:
            yield f"\n[GGUF STREAM ERROR] {str(e)}\n"

    # --------------------------------------------------
    def _stream_transformers(self, messages):
        chat = []

        for m in messages:
            if m["role"] in ("system", "user", "assistant"):
                chat.append({
                    "role": m["role"],
                    "content": m["content"],
                })

        prompt = self.tokenizer.apply_chat_template(
            chat,
            tokenize=False,
            add_generation_prompt=True,
        )

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        def run():
            if torch is None:
                raise RuntimeError("torch not available")

            with torch.inference_mode():
                inputs = self.tokenizer(
                    prompt,
                    return_tensors="pt",
                ).to(self.model.device)

                self.model.generate(
                    **inputs,
                    max_new_tokens=512,
                    streamer=streamer,
                )

        threading.Thread(target=run, daemon=True).start()

        for token in streamer:
            if token:
                yield clean_llm_output(token)







