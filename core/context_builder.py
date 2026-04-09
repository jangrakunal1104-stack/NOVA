def build_vision_prompt(vision_data, user_prompt):
    caption = vision_data.get("caption", "")
    ocr = vision_data.get("ocr", "")

    p = user_prompt.lower()

    # -----------------------------
    # TASK DETECTION (CRITICAL)
    # -----------------------------
    if "extract" in p or "text" in p:
        system = """You are a strict OCR extraction engine.

    You MUST follow these rules:

    - ONLY return text from the OCR input
    - DO NOT add any new content
    - DO NOT use prior knowledge
    - DO NOT hallucinate
    - If text is unclear, return it as-is
    - DO NOT explain anything

    Your entire response MUST be based ONLY on the OCR text provided.
    """

    elif any(k in ocr.lower() for k in [
        "version:", "ethernets", "dhcp", "inet", "<html", "function"
    ]):
        system = """You are an expert at reconstructing code/config from OCR.

Rules:
- Fix OCR errors
- Restore formatting
- Output clean code/config only
- NO explanation
"""

    else:
        system = """You are an image assistant.

Use OCR + caption to answer clearly.

Rules:
- Prefer OCR over caption
- Be concise
- Do not hallucinate
"""

    prompt = f"""
ONLY USE THE TEXT BELOW.

OCR TEXT:
----------------
{ocr}
----------------

TASK:
{user_prompt}

If the answer contains information not present in OCR TEXT, it is WRONG.
"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]