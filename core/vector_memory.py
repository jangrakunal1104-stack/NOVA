# core/vector_memory.py
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from datetime import datetime
import os
import uuid
from typing import List, Dict, Optional, Tuple


class VectorMemory:
    """
    Hierarchical Memory System for NOVA (Improved for 3B models)
    ------------------------------------------------------------
    Collections:
    - core_profile  → Permanent identity & strong preferences (always injected)
    - long_term     → Stable facts, skills, goals, preferences
    - episodic      → Specific events and recent context

    Key improvements:
    - Score thresholding (rejects weak matches)
    - Collection-specific retrieval strategies
    - Importance-aware + short context building (critical for 3B)
    - Stricter storage rules to reduce noise
    """

    # Distance thresholds (cosine distance — lower is better)
    # Chroma with cosine space returns distance = 1 - cosine_similarity
    THRESHOLDS = {
        "core_profile": 0.55,   # more tolerant — identity facts are precious
        "long_term": 0.45,
        "episodic": 0.40,
    }

    def __init__(self, persist_dir: str = "nova_memory_db"):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(path=persist_dir)

        self.embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        # === Hierarchical Collections ===
        self.core_profile = self.client.get_or_create_collection(
            name="core_profile",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine", "description": "Identity, name, strong preferences"}
        )

        self.long_term = self.client.get_or_create_collection(
            name="long_term",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine", "description": "Stable facts, skills, goals"}
        )

        self.episodic = self.client.get_or_create_collection(
            name="episodic",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine", "description": "Events and recent context"}
        )

        print(f"✅ NOVA Hierarchical VectorMemory initialized at {persist_dir}")

    # ------------------------------------------------------------------
    # Classification (stricter)
    # ------------------------------------------------------------------
    def classify_memory(self, text: str) -> Tuple[str, float]:
        """
        Returns (collection_name, importance).
        Pure questions and short noise are heavily down-weighted.
        """
        text = text.strip()
        text_lower = text.lower()

        # Hard reject pure questions and very short messages
        question_starters = (
            "what", "who", "how", "when", "where", "why", "is ", "are ", "do ", "does ",
            "can ", "could", "would", "tell me", "summarize", "explain", "which",
            "should i", "can you", "please"
        )

        if text_lower.endswith("?") or any(text_lower.startswith(q) for q in question_starters):
            return "episodic", 0.10          # almost never useful as knowledge

        if len(text) < 15:
            return "episodic", 0.15

        # === Core Profile (highest priority) ===
        core_signals = [
            "my name is", "i am known as", "i am kunal", "call me", "address me as",
            "i live in", "i am from", "my location is", "i stay in", "mr. black",
            "i am mr. black"
        ]
        if any(signal in text_lower for signal in core_signals):
            return "core_profile", 0.95

        # === Long-term ===
        long_term_signals = [
            "i prefer", "i always", "i never", "i like", "i hate", "i love",
            "my goal", "i work on", "i focus on", "i am a", "i specialize",
            "i want you to", "remember that", "my main", "dark theme", "dark mode",
            "my preference", "i usually", "i tend to"
        ]
        if any(signal in text_lower for signal in long_term_signals):
            return "long_term", 0.85

        # Default – only store reasonably long statements
        if len(text) > 45:
            return "episodic", 0.45

        return "episodic", 0.20

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def add(self, text: str, metadata: Optional[Dict] = None, collection: str = None):
        """
        Smart add with noise filtering.
        Very low importance items are simply dropped.
        """
        if not text or len(text.strip()) < 12:
            return

        if metadata is None:
            metadata = {}

        if collection is None:
            collection, importance = self.classify_memory(text)
            metadata["importance"] = importance
        else:
            metadata.setdefault("importance", 0.5)
            importance = metadata["importance"]

        # Drop pure noise
        if importance < 0.18:
            return

        metadata.update({
            "timestamp": datetime.now().isoformat(),
            "source": metadata.get("source", "chat"),
            "chat_id": metadata.get("chat_id", "unknown")
        })

        if collection == "core_profile":
            coll = self.core_profile
        elif collection == "long_term":
            coll = self.long_term
        else:
            coll = self.episodic

        # A plain millisecond timestamp can collide when multiple memories
        # are added in quick succession (fast typing, a tight loop, etc.),
        # silently overwriting an earlier memory that landed on the same
        # id. The uuid suffix guarantees uniqueness; the timestamp prefix
        # is kept for readability when inspecting the store directly.
        doc_id = f"{collection}_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"

        coll.add(
            documents=[text.strip()],
            metadatas=[metadata],
            ids=[doc_id]
        )

        print(f"[MEMORY] Stored in {collection} (imp={importance:.2f}): {text[:70]}...")

        self._prune_if_needed(collection)

    # ------------------------------------------------------------------
    # Pruning (bounded growth)
    # ------------------------------------------------------------------
    # Without this, long_term/episodic grow forever -- every message above
    # the noise threshold gets stored and never removed. Over months of
    # daily use that's thousands of entries, most of them low-value, which
    # slows down retrieval and dilutes what get_strong_context() surfaces.
    # core_profile is exempt: it's small (identity facts) and precious, so
    # it's never auto-pruned.
    PRUNE_CAPS = {"long_term": 500, "episodic": 800}

    @staticmethod
    def _select_ids_to_prune(ids, metadatas, max_entries):
        """
        Pure selection logic, no Chroma calls -- returns which ids to
        delete so the collection comes back under max_entries, dropping
        the lowest-importance entries first and, among ties, the oldest.
        Kept as a standalone static method so it's unit-testable without a
        live Chroma collection.
        """
        count = len(ids)
        if count <= max_entries:
            return []

        def sort_key(i):
            m = metadatas[i] or {}
            return (float(m.get("importance", 0.5)), m.get("timestamp", ""))

        order = sorted(range(count), key=sort_key)
        n_to_drop = count - max_entries
        return [ids[i] for i in order[:n_to_drop]]

    def _prune_if_needed(self, collection_name: str):
        max_entries = self.PRUNE_CAPS.get(collection_name)
        if max_entries is None:
            return

        coll = self.long_term if collection_name == "long_term" else self.episodic

        if coll.count() <= max_entries:
            return

        data = coll.get(include=["metadatas"])
        drop_ids = self._select_ids_to_prune(data["ids"], data["metadatas"], max_entries)

        if drop_ids:
            coll.delete(ids=drop_ids)
            print(f"[MEMORY] Pruned {len(drop_ids)} low-value entries from {collection_name} (cap={max_entries})")

    # ------------------------------------------------------------------
    # Retrieval (improved)
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        k: int = 6,
        collection: str = "long_term",
        min_importance: float = 0.0
    ) -> List[Dict]:
        """
        Search with score thresholding and optional importance filter.
        Returns list sorted by relevance (best first).
        """
        if collection == "core_profile":
            coll = self.core_profile
        elif collection == "long_term":
            coll = self.long_term
        else:
            coll = self.episodic

        # Over-fetch a bit so we can filter
        fetch_k = min(k * 3, 20)

        try:
            results = coll.query(
                query_texts=[query],
                n_results=fetch_k
            )
        except Exception as e:
            print(f"[MEMORY] Search error ({collection}): {e}")
            return []

        threshold = self.THRESHOLDS.get(collection, 0.45)
        memories = []

        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                dist = float(results["distances"][0][i]) if results.get("distances") else 1.0
                meta = results["metadatas"][0][i] or {}
                imp = float(meta.get("importance", 0.5))

                # Reject weak matches
                if dist > threshold:
                    continue
                if imp < min_importance:
                    continue

                memories.append({
                    "text": doc,
                    "metadata": meta,
                    "score": dist,          # lower = better
                    "importance": imp
                })

        # Sort by combined score (distance first, then importance)
        memories.sort(key=lambda x: (x["score"], -x["importance"]))
        return memories[:k]

    # ------------------------------------------------------------------
    # Context building (optimized for 3B)
    # ------------------------------------------------------------------
    def get_strong_context(self, query: str = None, max_chars: int = 1800) -> str:
        """
        Build a clean, short, high-signal memory block for the 3B model.

        Design principles for small models:
        - Keep total memory under ~1800 characters
        - Core profile always present (even if short)
        - Only high-relevance long-term + episodic
        - Clear separation and instructions
        """
        query = (query or "Kunal Mr. Black personal identity preferences goals skills location").strip()

        # 1. Core profile – always try to get something useful
        core_results = self.search(
            query="name identity location preferences Mr. Black Kunal",
            k=6,
            collection="core_profile",
            min_importance=0.3
        )

        # 2. Long-term – query-aware
        long_results = self.search(
            query=query,
            k=5,
            collection="long_term",
            min_importance=0.4
        )

        # 3. Episodic – only recent / highly relevant
        episodic_results = self.search(
            query=query,
            k=3,
            collection="episodic",
            min_importance=0.35
        )

        parts = []
        parts.append("FACTS ABOUT THE USER (Mr. Black / Kunal):")
        parts.append("Use these only when relevant. Do not recite the whole list.")

        # Core
        if core_results:
            parts.append("\n[CORE IDENTITY]")
            for r in core_results:
                parts.append(f"• {r['text']}")
        else:
            parts.append("\n[CORE IDENTITY]")
            parts.append("• Name: Kunal (Mr. Black)")

        # Long-term
        if long_results:
            parts.append("\n[LONG-TERM KNOWLEDGE]")
            for r in long_results:
                parts.append(f"• {r['text']}")

        # Episodic
        if episodic_results:
            parts.append("\n[RECENT CONTEXT]")
            for r in episodic_results:
                parts.append(f"• {r['text']}")

        context = "\n".join(parts)

        # Hard length limit for 3B safety
        if len(context) > max_chars:
            context = context[:max_chars].rsplit("\n", 1)[0] + "\n…"

        return context

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def stats(self) -> Dict:
        return {
            "core_profile": self.core_profile.count(),
            "long_term": self.long_term.count(),
            "episodic": self.episodic.count(),
            "db_path": self.persist_dir
        }

    def clear_collection(self, collection: str):
        """Utility for testing / reset"""
        if collection == "core_profile":
            self.client.delete_collection("core_profile")
            self.core_profile = self.client.get_or_create_collection(
                name="core_profile",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
        elif collection == "long_term":
            self.client.delete_collection("long_term")
            self.long_term = self.client.get_or_create_collection(
                name="long_term",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
        elif collection == "episodic":
            self.client.delete_collection("episodic")
            self.episodic = self.client.get_or_create_collection(
                name="episodic",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
        print(f"[MEMORY] Cleared collection: {collection}")

    def debug_search(self, query: str):
        """Print what would be retrieved — useful for testing"""
        print(f"\n=== DEBUG SEARCH: '{query}' ===")
        for coll_name in ["core_profile", "long_term", "episodic"]:
            results = self.search(query, k=4, collection=coll_name)
            print(f"\n[{coll_name}] ({len(results)} kept)")
            for r in results:
                print(f"  score={r['score']:.3f} imp={r['importance']:.2f} | {r['text'][:80]}")