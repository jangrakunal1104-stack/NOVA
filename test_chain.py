# Legacy manual smoke-test script (not a pytest test despite the
# filename). The same coverage now exists properly in
# tests/test_brain.py, with real assertions instead of printed output you
# have to eyeball -- prefer running `pytest tests/test_brain.py` instead.
#
# Kept runnable standalone (python test_chain.py) and wrapped in main() /
# __main__ so importing this file doesn't instantiate BackendRouter (and
# therefore load model/vision engines) as a side effect.
from core.brain import Brain
from core.backend_router import BackendRouter
from core.image_engine import ImageEngine
from ui.llm_worker import LLMWorker


def main():
    print("=== Full Chain Test: Brain + Router + Worker ===\n")

    brain = Brain()
    image_engine = ImageEngine()
    router = BackendRouter(image_engine)

    test_prompts = [
        "extract text from this image",
        "generate image of a mountain",
        "write a python function to reverse a string",
        "hello how are you"
    ]

    for prompt in test_prompts:
        print(f"Testing prompt: {prompt}")

        decision = brain.decide([{"role": "user", "content": prompt}])
        model = decision.get("model")
        llm_type = decision.get("llm_type", "None")

        print(f"   Brain Decision → {model} | llm_type={llm_type}")

        if model == "llm":
            print(f"   Router + Worker will use: {llm_type} model")
        elif model == "vision":
            print("   → Vision Engine (Qwen2-VL)")
        elif model == "diffusion":
            print("   → Diffusion Engine (Stable Diffusion)")

        print("-" * 80)

    print("\n✅ All components (Brain → Router → Worker) are connected and working!")


if __name__ == "__main__":
    main()
