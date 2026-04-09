import subprocess
import os
python_path = os.path.expanduser("~/ai-stack/genv/bin/python")
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
class VisionEngine:
    def __init__(self):
        self.proc = None

    def load(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                return  # still running
            else:
                self.proc = None  # crashed → reset

        self.proc = subprocess.Popen(
            [
                python_path,
                os.path.join(BASE_DIR, "core", "vision_service.py")
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,   # 🔥 IMPORTANT
            text=True
        )
        if self.proc.poll() is not None:
            raise RuntimeError("Vision process failed to start")
        # 🔥 consume startup logs until READY
        while True:
            line = self.proc.stdout.readline().strip()

            if not line:
                continue

            # stop when service is ready
            if "READY" in line:
                break

    def describe_image(self, image_path, prompt):
        # 🔥 restart if crashed
        if self.proc is None or self.proc.poll() is not None:
            
            self.proc = None
            self.load()

        try:
            self.proc.stdin.write(f"{image_path}||{prompt}\n")
            self.proc.stdin.flush()
        except:
            
            self.proc = None
            self.load()
            self.proc.stdin.write(f"{image_path}||{prompt}\n")
            self.proc.stdin.flush()

        
        while True:
            line = self.proc.stdout.readline().strip()

            if not line:
                continue

            # 🔥 skip service logs
            if line.startswith("[VISION SERVICE]"):
                continue

            # 🔥 skip empty / noise
            if line.startswith("[") and "ERROR" not in line:
                continue

            result = line
            break

        

        return result

    def unload(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None