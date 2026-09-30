# finalize_memory_dataset.py
import json
import random
from pathlib import Path

print("=== Final Clean Memory Dataset for LoRA ===")

DATASET_DIR = Path("datasets")
OUTPUT_FILE = "nova_final_memory_dataset.jsonl"

all_examples = []

# Load the two memory datasets
files_to_load = ["train.jsonl", "nikolas_memory_recall_dataset.jsonl"]

for filename in files_to_load:
    file_path = DATASET_DIR / filename
    if not file_path.exists():
        print(f"⚠️ Missing: {filename}")
        continue

    print(f"Loading {filename}...")
    count = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                text = str(item.get("Expected Answer") or item.get("output") or item.get("text") or str(item))
                if text.strip():
                    all_examples.append({
                        "instruction": "You are Nova, Mr. Black's personal AI companion. You have perfect memory. Never hallucinate or add external knowledge.",
                        "input": "Tell me everything you know about me right now.",
                        "output": f"Here is everything I know about you, Sir:\n• {text[:650]}"
                    })
                    count += 1
            except:
                continue
    print(f"  Loaded {count} examples from {filename}")

# Add your personal facts (strong emphasis)
custom_facts = [
    "I am currently deep into Linux kernel exploitation and want to master pwn challenges.",
    "My favorite RE tool is Ghidra because I hate bloated GUIs. I love minimal terminal tools.",
    "My goal is to become the best at binary exploitation in India this year.",
]

for fact in custom_facts * 10:
    all_examples.append({
        "instruction": "You are Nova, Mr. Black's personal AI companion. You have perfect memory. Never hallucinate.",
        "input": "Tell me everything you know about me right now.",
        "output": f"Here is everything I know about you, Sir:\n• {fact}\nThis is all the stored information I have."
    })

random.shuffle(all_examples)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    for ex in all_examples:
        f.write(json.dumps(ex) + "\n")

print(f"\n✅ FINAL DATASET READY!")
print(f"Total examples: {len(all_examples)}")
print(f"Saved as: {OUTPUT_FILE}")
print("\nYou can now proceed to LoRA training.")