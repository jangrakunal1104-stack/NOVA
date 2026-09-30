from core.image_engine import SD15_PATH
from core.gpu_arbiter import GPUArbiter
from core.model_loader import ModelLoader
from core.vision_qwen import QwenVision
import torch


class BackendRouter:
    def __init__(self, image_engine):
        self.model_loader = ModelLoader()
        self.vision_engine = QwenVision()
        self.image_engine = image_engine
        self.arbiter = GPUArbiter(
            vision_engine=self.vision_engine,
            image_engine=self.image_engine
        )

    def run_llm(self, messages, llm_type=None):
        def _run():
            final_llm_type = llm_type or "chat"
            self.model_loader.switch_model(final_llm_type)   # ← Use switch
            yield from self.model_loader.generate_stream(messages, final_llm_type)
        return self.arbiter.run_text(_run)

    def run_vision(self, image_path, user_prompt):
        def _run():
            print(f"[VISION] Qwen2-VL called → {image_path}")
            try:
                result = self.vision_engine.extract(image_path, user_prompt)
                print(f"[VISION] Extracted: {result[:200]}...")   # Debug
                return {"ocr": result, "type": "qwen"}
            except Exception as e:
                print(f"[VISION ERROR] {e}")
                return {"ocr": f"Vision failed: {str(e)}", "type": "error"}
        
        return self.arbiter.run_vision(_run)

    def run_diffusion(self, payload: dict):
        def _run():
            print("[DIFFUSION] Starting generation...")
            if self.image_engine.pipeline is None:
                print("[DIFFUSION] Loading SD15 model...")
                load_result = self.image_engine.load_model(
                    SD15_PATH, 
                    device="gpu" if torch.cuda.is_available() else "cpu"
                )
                print(f"[DIFFUSION] Load result: {load_result}")
            return self.image_engine.run_generation(payload)

        return self.arbiter.run_diffusion(_run)