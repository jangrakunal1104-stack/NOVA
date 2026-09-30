# Legacy manual smoke-test script (not a pytest test despite the
# filename) -- predates the current single-model setup and points at
# nova_jarvis_merged, which the app no longer uses (see
# core/model_loader.py, which now loads models/gguf/nova_mrblack_q8_0.gguf
# instead). Update model_path below if you want to run this against a
# model you still have on disk.
#
# Wrapped in main() / __main__ so importing this file (e.g. an editor's
# "go to definition", or an earlier version of pytest that didn't respect
# pytest.ini's testpaths) doesn't try to load a model as a side effect.
from llama_cpp import Llama


def main():
    print("Loading your trained Jarvis...")

    model = Llama(
        model_path="/home/panda/ai-stack/NOVA/nova_jarvis_merged",
        n_gpu_layers=35,          # Use GPU (adjust between 30-40 if needed)
        n_ctx=8192,
        chat_format="chatml",
        verbose=False
    )

    print("✅ Personalized Jarvis loaded successfully!\n")

    response = model.create_chat_completion(
        messages=[
            {"role": "system", "content": "You are Nova, Mr. Black's personal Jarvis. Be direct, competent and remember everything about him."},
            {"role": "user", "content": "What is my name and what do I want to achieve in life?"}
        ],
        max_tokens=400,
        temperature=0.7
    )

    print(response['choices'][0]['message']['content'])


if __name__ == "__main__":
    main()
