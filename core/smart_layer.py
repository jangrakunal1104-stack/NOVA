import black
import re


class SmartLayer:

    def __init__(self, router):
        self.router = router

    def refine_ocr(self, ocr_text):

        # =========================
        # STEP 1 — FIX OCR ONLY (NO FORMAT FORCE)
        # =========================
        prompt = f"""Fix OCR errors in this Python code.

Rules:
- Keep structure simple
- Do NOT compress into one line
- Do NOT add explanations
- Keep output multi-line

{ocr_text}
"""

        code = ""

        for chunk in self.router.run_llm(
            [{"role": "user", "content": prompt}],
            llm_type="chat"
        ):
            code += chunk

        # =========================
        # STEP 2 — MINIMAL NORMALIZATION (ONLY SPLIT)

        # =========================
        
        code = code.strip()

        code = code.replace(" class ", "\nclass ")
        code = code.replace(" def ", "\ndef ")

        # split statements safely
        code = re.sub(r"\)\s+", ")\n", code)
        code = re.sub(r":\s+", ":\n", code)
        code = re.sub(r"(\d)\s+(?=[a-zA-Z_])", r"\1\n", code)
        # =========================
        # STEP 3 — VERY LIGHT BLACK (SAFE MODE)
        # =========================
        try:
            code = black.format_str(code, mode=black.FileMode())
        except Exception:
            pass

        return code.strip()