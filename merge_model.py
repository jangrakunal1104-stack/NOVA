# merge_model.py
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer
import torch

model_path = "nova_jarvis"

print("Merging LoRA adapter...")
model = AutoPeftModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype=torch.float16,
    device_map="auto"
)

merged_model = model.merge_and_unload()

merged_model.save_pretrained("nova_jarvis_merged")
tokenizer = AutoTokenizer.from_pretrained(model_path)
tokenizer.save_pretrained("nova_jarvis_merged")

print("✅ Model merged and saved to 'nova_jarvis_merged' folder")