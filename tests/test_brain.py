"""
Tests for core.brain.Brain -- the keyword-based intent router that decides
whether a message goes to LLM chat, live search, image generation, or
vision. No external dependencies.
"""
from core.brain import Brain


def decide(msg, attachments=None):
    b = Brain()
    return b.decide([{"role": "user", "content": msg}], attachments=attachments)


def test_image_generation_routes_to_diffusion():
    assert decide("generate image of a mountain")["model"] == "diffusion"


def test_news_query_routes_to_search():
    assert decide("latest news on the stock market")["model"] == "search"


def test_code_request_routes_to_llm():
    assert decide("write a python function to reverse a string")["model"] == "llm"


def test_plain_chat_routes_to_llm():
    assert decide("hello how are you")["model"] == "llm"


def test_image_attachment_routes_to_vision():
    d = decide("what does this say", attachments=[{"type": "image", "path": "/tmp/fake.png"}])
    assert d["model"] == "vision"
    assert d["input"]["image_path"] == "/tmp/fake.png"


def test_empty_messages_defaults_to_chat():
    b = Brain()
    d = b.decide([])
    assert d["model"] == "llm"


# --- Regression tests for the word-boundary / ordering fixes ---

def test_classical_does_not_false_positive_on_class_keyword():
    # "classical" contains "class" as a raw substring; naive `in` matching
    # used to route this to CODE REQUEST.
    assert decide("tell me about classical music history")["model"] == "llm"


def test_subscription_does_not_false_positive_on_script_keyword():
    # "subscription" contains "script" as a raw substring.
    assert decide("please help me cancel my subscription")["model"] == "llm"


def test_search_wins_over_incidental_image_noun_in_query():
    # "picture of" is an IMAGE_KEYWORDS phrase, but "search for" makes the
    # actual intent unambiguous -- should search, not generate an image.
    assert decide("search for a picture of the eiffel tower")["model"] == "search"


def test_attached_image_wins_over_search_phrase_in_text():
    # An actually-attached image is a stronger signal than a search phrase
    # appearing incidentally in the accompanying text.
    d = decide("what's the latest news about this",
                attachments=[{"type": "image", "path": "/tmp/fake.png"}])
    assert d["model"] == "vision"
