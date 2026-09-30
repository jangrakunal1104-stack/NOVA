#!/usr/bin/env python3
import os
import gc
import torch
from typing import Generator

home = os.path.expanduser("~")

try:
    from llama_cpp import Llama
except Exception as e:
    print(f"[MODEL LOADER] Error: {e}")
    Llama = None

from core.gpu_manager import GPUManager


class ModelLoader:
    def __init__(self):
        self.model = None
        self.model_path = None

        # === SINGLE MODEL SETUP ===
        self.model_path = f"{home}/ai-stack/NOVA/models/gguf/nova_mrblack_q8_0.gguf"
        print(f"[MODEL] Using single fine-tuned model: nova_mrblack_q8_0.gguf (for both chat & code)")

    def unload_model(self):
        if self.model is not None:
            try:
                self.model.close()
            except Exception:
                pass
            try:
                del self.model
            except Exception:
                pass
            self.model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            GPUManager.hard_cleanup("llm_unload", aggressive=True)
            print("[MODEL LOADER] ✅ Model unloaded")
        else:
            print("[MODEL LOADER] Already unloaded")

    def load(self, llm_type: str = "chat"):
        """Load the single model (no more switching)"""
        if self.model:
            print(f"[MODEL] Already loaded")
            return {"status": "ok"}

        self.unload_model()

        print(f"[MODEL] Loading nova_mrblack_q8_0.gguf on RTX 3060...")

        try:
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=8192,
                n_gpu_layers=-1,
                n_batch=512,
                n_threads=8,
                main_gpu=0,
                offload_kqv=True,
                flash_attn=True,
                verbose=False,
            )
            print(f"[GPU SUCCESS] Fine-tuned model loaded with full GPU")
            return {"status": "ok"}
        except Exception as e:
            print(f"[LOAD ERROR] {e}")
            self.unload_model()
            return {"status": "error", "error": str(e)}

    def switch_model(self, llm_type: str = "chat"):
        """No more switching needed"""
        if self.model is None:
            return self.load(llm_type)
        print(f"[MODEL] Already loaded (single model mode)")
        return {"status": "ok"}

    def generate_stream(self, messages, llm_type: str = "chat") -> Generator[str, None, None]:
        if not self.model:
            yield "[ERROR] Model not loaded"
            return

        print(f"[MODEL] Using fine-tuned nova_mrblack model")
        yield from self._raw_stream(messages)

    def _raw_stream(self, messages):
        if not self.model:
            yield "[ERROR] Model not loaded"
            return

        self.model.reset()

        # Strong continuity-first system prompt
        base_system = (
            "You are Nova, Mr. Black's personal AI companion.\n"
            "Always address him as Sir or Mr. Black.\n\n"
            "CRITICAL RULES FOR CONVERSATION:\n"
            "1. You MUST maintain perfect continuity with the previous messages.\n"
            "2. When the user says 'it', 'this', 'that', 'them', 'the topic', etc., "
            "you MUST resolve the reference from the most recent user and assistant messages.\n"
            "3. Never ask the user to clarify what 'it' means if the previous turn already made the topic clear.\n"
            "4. Do not change the subject unless the user clearly starts a new topic.\n"
            "5. If a memory block is provided, treat those facts as true about the user."
        )

        system_parts = [base_system]
        conversation = []

        for msg in messages:
            role = (msg.get("role") or "").lower()
            content = (msg.get("content") or "").strip()
            if not content:
                continue

            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                conversation.append({"role": role, "content": content})

        final_system = "\n\n".join(system_parts)

        # Build prompt
        prompt = f"<|im_start|>system\n{final_system}<|im_end|>\n"

        for msg in conversation:
            prompt += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"

        prompt += "<|im_start|>assistant\n"

        

        for chunk in self.model(
            prompt,
            max_tokens=1024,
            temperature=0.55,          # lower for better adherence
            top_p=0.85,
            stream=True,
            repeat_penalty=1.15,
        ):
            if chunk and "choices" in chunk:
                delta = chunk["choices"][0].get("text", "")
                if delta:
                    yield delta