import torch
import gc
import time

class GPUManager:

    @staticmethod
    def hard_cleanup(tag="", aggressive=True):
        gc.collect()
        if torch.cuda.is_available():
            if aggressive:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                # Extra aggressive step
                torch.cuda.reset_peak_memory_stats()
                time.sleep(0.2)
            torch.cuda.synchronize()
            free = torch.cuda.mem_get_info()[0] / 1e9
            print(f"[GPU] Cleanup [{tag}] | Free: {free:.1f} GB")
        else:
            print(f"[GPU] Cleanup [{tag}] (CPU only)")

    @staticmethod
    def assert_free(min_free_gb=4.0):   # Lowered threshold
        if not torch.cuda.is_available():
            return
        free = torch.cuda.mem_get_info()[0] / 1e9
        if free < min_free_gb:
            print(f"[GPU] Low VRAM ({free:.1f}GB). Forcing aggressive cleanup...")
            GPUManager.hard_cleanup("pre_assert_aggressive", aggressive=True)
            free = torch.cuda.mem_get_info()[0] / 1e9
            if free < min_free_gb - 2:
                raise RuntimeError(f"Not enough VRAM. Free: {free:.1f}GB, Required: {min_free_gb}GB")
        print(f"[GPU] VRAM OK: {free:.1f} GB free")

    @staticmethod
    def get_free():
        if not torch.cuda.is_available():
            return 0, 0
        free, total = torch.cuda.mem_get_info()
        return free / 1e9, total / 1e9