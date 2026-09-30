from core.gpu_manager import GPUManager
import time

class GPUArbiter:
    def __init__(self, vision_engine=None, image_engine=None):
        self.vision_engine = vision_engine
        self.image_engine = image_engine

    def run_text(self, fn):
        GPUManager.hard_cleanup("before_llm", aggressive=True)
        try:
            return fn()
        finally:
            GPUManager.hard_cleanup("after_llm", aggressive=True)

    def run_vision(self, fn):
        # Unload LLM + Diffusion before Vision
        if hasattr(self.vision_engine, 'unload'):
            self.vision_engine.unload()
        GPUManager.hard_cleanup("before_vision", aggressive=True)
        try:
            return fn()
        finally:
            GPUManager.hard_cleanup("after_vision", aggressive=True)

    def run_diffusion(self, fn):
        print("[GPU] Preparing for Diffusion (High VRAM)...")
        # Unload everything else before diffusion
        if self.vision_engine and hasattr(self.vision_engine, 'unload'):
            self.vision_engine.unload()
        GPUManager.hard_cleanup("before_diffusion", aggressive=True)
        
        GPUManager.assert_free(min_free_gb=5.0)   # Slightly lowered
        
        try:
            return fn()
        finally:
            GPUManager.hard_cleanup("after_diffusion", aggressive=True)
            time.sleep(0.5)