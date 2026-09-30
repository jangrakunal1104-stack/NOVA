"""
Tests for core.vector_memory.VectorMemory. Uses a real Chroma instance
(chromadb is a hard runtime dependency of the app itself, so this doesn't
add anything you don't already need installed) pointed at a temp
directory via the `vm` fixture -- never touches the real nova_memory_db.

Note: the first run may take a few seconds while sentence-transformers
loads/downloads the all-MiniLM-L6-v2 embedding model, same as it does the
first time you launch desktop.py.
"""
import pytest

from core.vector_memory import VectorMemory


@pytest.fixture
def vm(tmp_path):
    return VectorMemory(persist_dir=str(tmp_path / "vm_db"))


def test_classify_memory_core_profile(vm):
    # classify_memory() is pure string logic (no Chroma I/O), but we still
    # go through the `vm` fixture rather than a bare VectorMemory() so we
    # never accidentally touch the real nova_memory_db on disk.
    coll, imp = vm.classify_memory("My name is Kunal and call me Mr. Black")
    assert coll == "core_profile"
    assert imp >= 0.9


def test_classify_memory_question_is_low_importance_episodic(vm):
    coll, imp = vm.classify_memory("what time is it right now")
    assert coll == "episodic"
    assert imp < 0.2


def test_classify_memory_preference_is_long_term(vm):
    coll, imp = vm.classify_memory("I prefer using dark mode in every app")
    assert coll == "long_term"


def test_add_and_search_round_trip(vm):
    # Query deliberately shares strong lexical/semantic overlap with the
    # stored text ("prefer", "tool", "reverse engineering") so this passes
    # reliably against the real all-MiniLM-L6-v2 embeddings and the
    # long_term collection's 0.45 cosine-distance threshold -- a vaguer
    # query ("what tool do I prefer") was too semantically distant from
    # "Ghidra" specifically and could fall on either side of the cutoff.
    vm.add("I prefer using Ghidra for reverse engineering work", metadata={"chat_id": "1"})
    results = vm.search(
        "what tool do I prefer for reverse engineering",
        collection="long_term",
        min_importance=0.0,
    )
    assert any("Ghidra" in r["text"] for r in results)


def test_get_strong_context_includes_core_identity_header(vm):
    ctx = vm.get_strong_context("hello")
    assert "FACTS ABOUT THE USER" in ctx
    assert "[CORE IDENTITY]" in ctx


def test_very_short_or_noisy_text_is_dropped(vm):
    vm.add("ok")  # too short (< 12 chars)
    assert vm.stats()["episodic"] == 0
    assert vm.stats()["long_term"] == 0
    assert vm.stats()["core_profile"] == 0


# --- Pruning (bounded growth) ---

def test_select_ids_to_prune_drops_lowest_importance_first():
    ids = [f"id{i}" for i in range(10)]
    metas = [{"importance": (i % 5) / 5.0, "timestamp": f"t{i}"} for i in range(10)]

    drop = VectorMemory._select_ids_to_prune(ids, metas, max_entries=7)
    assert len(drop) == 3

    kept = [i for i in ids if i not in drop]
    dropped_importance = max(metas[ids.index(i)]["importance"] for i in drop)
    kept_importance = min(metas[ids.index(i)]["importance"] for i in kept)
    assert dropped_importance <= kept_importance


def test_select_ids_to_prune_is_noop_under_cap():
    ids = ["a", "b", "c"]
    metas = [{"importance": 0.5, "timestamp": "t"}] * 3
    assert VectorMemory._select_ids_to_prune(ids, metas, max_entries=10) == []


def test_long_term_collection_stays_capped_after_many_adds(vm):
    vm.PRUNE_CAPS = {"long_term": 5, "episodic": 5}
    for i in range(8):
        vm.add(f"I prefer using tool number {i} for my daily workflow", metadata={"chat_id": "t"})
    assert vm.long_term.count() == 5


def test_core_profile_is_never_auto_pruned(vm):
    vm.PRUNE_CAPS = {"long_term": 2, "episodic": 2}
    for i in range(6):
        vm.add(f"My name is Kunal, entry number {i} about myself", metadata={"chat_id": "t"})
    assert vm.core_profile.count() == 6


def test_rapid_adds_do_not_collide_on_id(vm):
    # Regression: doc_id used to be a bare millisecond timestamp, so
    # several add() calls within the same millisecond could silently
    # overwrite each other under the same id.
    for i in range(20):
        vm.add(f"I prefer distinct memory entry number {i} for this test", metadata={"chat_id": "t"})
    assert vm.long_term.count() == 20
