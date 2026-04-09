import torch
import gc


class GPUManager:

    @staticmethod
    def hard_cleanup(tag="", aggressive=True):
        gc.collect()

        if torch.cuda.is_available():
            if aggressive:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()

            torch.cuda.synchronize()

    @staticmethod
    def assert_free(min_free_gb=4):
        if not torch.cuda.is_available():
            return

        free = torch.cuda.mem_get_info()[0] / 1e9

        if free < min_free_gb:
            raise RuntimeError(
                f"Not enough VRAM. Required: {min_free_gb} GB, Available: {free:.2f} GB"
            )

    @staticmethod
    def get_free():
        if not torch.cuda.is_available():
            return 0, 0

        free, total = torch.cuda.mem_get_info()
        return free / 1e9, total / 1e9