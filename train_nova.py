# train_memory_lora.py
import torch
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

print("=== NOVA Memory LoRA Training - Optimized for RTX 3060 ===")

# ====================== CONFIG ======================
BASE_MODEL = "unsloth/nova_mrblack_q8_0.gguf"   # Your main model
OUTPUT_DIR = "nova_memory_lora"
MAX_EXAMPLES = 15000                            # Good balance (out of 70k)

# Load dataset
dataset = load_dataset("json", data_files="nova_final_memory_dataset.jsonl", split="train")
dataset = dataset.shuffle(seed=42).select(range(min(MAX_EXAMPLES, len(dataset))))

print(f"Training on {len(dataset)} high-quality memory examples")

# ====================== LOAD MODEL ======================
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=4096,
    dtype=None,                    # Auto
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing=True,
    random_state=42,
)

# ====================== TRAINING ======================
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=4096,
    dataset_num_proc=2,
    packing=False,
    args=TrainingArguments(
        per_device_train_batch_size=1,           # Safe for 3060
        gradient_accumulation_steps=16,          # Effective batch ~16
        warmup_steps=20,
        max_steps=450,                           # Good quality (~1.5-2.5 hours)
        learning_rate=2e-4,
        fp16=True,
        logging_steps=20,
        output_dir=OUTPUT_DIR,
        optim="adamw_8bit",
        save_strategy="steps",
        save_steps=150,
        report_to="none",
        save_total_limit=2,
    ),
)

print("🚀 Starting LoRA training for Memory Recall...")
trainer.train()

# Save
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"\n✅ Training Finished!")
print(f"LoRA saved in: {OUTPUT_DIR}")
print("You can now use this LoRA for strong memory recall.")