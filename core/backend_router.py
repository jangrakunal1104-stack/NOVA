from core.image_engine import SD15_PATH
from core.vision_engine import VisionEngine
from core.gpu_arbiter import GPUArbiter
from core.model_loader import ModelLoader
from core.vision_pipeline import process_image
import os

class BackendRouter:

    def __init__(self, image_engine):
        self.model_loader = ModelLoader()
        self.image_engine = image_engine
        self.vision_engine = VisionEngine()

        self.arbiter = GPUArbiter(
            vision_engine=self.vision_engine,
            image_engine=self.image_engine
        )

    # =============================
    # LLM (FIXED)
    # =============================
    def run_llm(self, messages, llm_type=None):

        def _run():
            prompt = messages[-1]["content"].lower() if messages else ""

            # -------------------------
            # AUTO ROUTING
            # -------------------------
            if any(k in prompt for k in ["code", "python", "script", "program"]):
                llm_type = "code"
            else:
                llm_type = "chat"

            print(f"[ROUTER] AUTO TYPE: {llm_type}")

            model_path = self.model_loader.models.get(llm_type)

            if not model_path:
                yield "[ERROR] Unknown model type"
                return

            current = self.model_loader.get_loaded_model_name()

            if current != os.path.basename(model_path):
                print(f"[ROUTER] Loading model: {llm_type}")
                self.model_loader.load(model_path, device="gpu")

            for token in self.model_loader.generate_stream(messages):
                yield token

        return self.arbiter.run_text(_run)

    # =============================
    # VISION
    # =============================
    def run_vision(self, image_path, user_prompt):
        print(f"[VISION] Processing: {image_path}")

        result = process_image(image_path, user_prompt)

        if isinstance(result, dict) and "ocr" in result:
            return result

        return str(result)

    # =============================
    # DIFFUSION
    # =============================
    def run_diffusion(self, payload: dict):

        def _run():
            if self.image_engine.pipeline is None:
                print("[ROUTER] Loading diffusion model...")
                self.image_engine.load_model(
                    self.image_engine.model_path or SD15_PATH,
                    device="gpu"
                )

            res = self.image_engine.run_generation({
                "prompt": payload.get("prompt", ""),
                "width": payload.get("width", 768),
                "height": payload.get("height", 768),
                "steps": payload.get("steps", 35),
                "cfg": payload.get("cfg", 8.0),
                "thumb": payload.get("thumb", 256),
            })

            return res

        return _run()