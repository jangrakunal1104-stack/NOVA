

class GPUArbiter:
    def __init__(self, vision_engine=None, image_engine=None):
        
        self.vision_engine = vision_engine
        self.image_engine = image_engine

    # -----------------------------
    # TEXT (LLM)
    # -----------------------------
    def run_text(self, fn):
        return fn()

    # -----------------------------
    # VISION
    # -----------------------------
    def run_vision(self, fn):
        return fn()

    # -----------------------------
    # DIFFUSION
    # -----------------------------
    def run_diffusion(self, fn):
        return fn()
