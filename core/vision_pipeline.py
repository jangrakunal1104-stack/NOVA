from PIL import Image
import pytesseract
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
import numpy as np
import cv2
import re


# =============================
# GLOBALS (LAZY LOAD)
# =============================
device = "cuda" if torch.cuda.is_available() else "cpu"

processor = None
model = None

TESS_CONFIG = r"--oem 3 --psm 6"


# =============================
# LOAD MODEL (LAZY)
# =============================
def load_blip():
    global processor, model

    if processor is None or model is None:
        print("[VISION] Loading BLIP model...")

        processor = BlipProcessor.from_pretrained(
            "Salesforce/blip-image-captioning-base"
        )

        model = BlipForConditionalGeneration.from_pretrained(
            "Salesforce/blip-image-captioning-base"
        ).to(device)

        model.eval()


# =============================
# SAFE IMAGE LOAD
# =============================
def load_image(image_path):
    img = Image.open(image_path).convert("RGB")
    return Image.fromarray(np.array(img))  # break cache


# =============================
# CAPTION
# =============================
def get_caption(image_path):
    load_blip()

    image = load_image(image_path)
    inputs = processor(image, return_tensors="pt").to(device)

    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=50)

    caption = processor.decode(out[0], skip_special_tokens=True)
    return caption.strip()


# =============================
# OCR
# =============================
def get_ocr(image_path):
    img = cv2.imread(image_path)

    img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    # threshold (good for code)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    text = pytesseract.image_to_string(thresh, config=TESS_CONFIG)
    return text.strip()


# =============================
# CLEAN OCR
# =============================
def clean_ocr(text):
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        line = line.strip()

        if len(line) < 3:
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


# =============================
# MAIN PIPELINE
# =============================
def process_image(image_path, user_prompt):
    caption = get_caption(image_path)
    ocr_raw = get_ocr(image_path)
    ocr_text = clean_ocr(ocr_raw)

    return {
        "caption": caption,
        "ocr": ocr_text,
        "type": "auto"
    }


# =============================
# SIMPLE DETECTOR
# =============================
def is_code(text):
    if not text:
        return False

    keywords = [
        "network", "version", "ethernets",
        "dhcp", "inet", "nameserver",
        "<html", "function", "script"
    ]

    return sum(k in text.lower() for k in keywords) >= 2