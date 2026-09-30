# vision_qwen.py - Stabilized
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import torch
from PIL import Image
from pathlib import Path
import os

from core.gpu_manager import GPUManager

class QwenVision:
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.model_path = Path.home() / "ai-stack/NOVA/models/vision/Qwen2-VL-2B-Instruct"

    def load(self):
        if self.model is not None:
            return

        print(f"[VISION] Loading Qwen2-VL-2B...")
        GPUManager.hard_cleanup("before_vision_load", aggressive=True)

        try:
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                str(self.model_path),
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto",
                trust_remote_code=True,
                local_files_only=True
            )
            
            self.processor = AutoProcessor.from_pretrained(
                str(self.model_path),
                trust_remote_code=True,
                local_files_only=True
            )
            
            print(f"[VISION] ✅ Qwen2-VL-2B loaded on {self.device}")
        except Exception as e:
            print(f"[VISION ERROR] {e}")
            self.unload()
            raise

    def unload(self):
        if self.model:
            del self.model
            del self.processor
            self.model = self.processor = None
            GPUManager.hard_cleanup("vision_unload", aggressive=True)
            torch.cuda.empty_cache() if torch.cuda.is_available() else None

    def extract(self, image_path: str, prompt: str = "Describe this image in detail."):
        # Force unload other models before loading Vision
        GPUManager.hard_cleanup("pre_vision", aggressive=True)
        if self.model is None or self.processor is None:
            self.load()

        try:
            image = Image.open(image_path).convert("RGB")
            
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt}
                ]
            }]

            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.processor(text=[text], images=[image], padding=True, return_tensors="pt").to(self.device)

            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                temperature=0.1,
                do_sample=False,
                eos_token_id=self.processor.tokenizer.eos_token_id
            )

            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            response = generated_text.split("assistant")[-1].strip()
            
            return response

        except Exception as e:
            print(f"[VISION] Processing error: {e}")
            return f"Vision error: {str(e)}"