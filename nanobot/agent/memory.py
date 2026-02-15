"""Memory system for persistent agent memory."""


from pathlib import Path

from nanobot.agent.vector_store import VectorStore
from nanobot.utils.helpers import ensure_dir


class MemoryStore:
    """Three-layer memory: MEMORY.md (facts) + HISTORY.md (log) + Vector DB (semantics)."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self.vector_store = VectorStore(workspace)

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")
        # Also index long-term memory chunks (basic split)
        if content:
            chunks = content.split('\n\n')
            for chunk in chunks:
                if len(chunk) > 50:
                    self.vector_store.add(chunk, {"source": "long_term_memory"})

    def append_history(self, entry: str, metadata: dict | None = None) -> None:
        """Append entry to history log and vector index."""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")
            
        # Add to vector store for semantic search
        if len(entry) > 30:  # Skip very short entries
            meta = metadata or {}
            meta["source"] = "history_log"
            self.vector_store.add(entry, meta)

    def get_memory_context(self) -> str:
        """Get memory context for the agent (only long-term memory)."""
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    def semantic_search(self, query: str, limit: int = 5) -> str:
        """Retrieve relevant context via vector search."""
        results = self.vector_store.query(query, n_results=limit)
        if not results:
            return ""
            
        context = "## Relevant Past Context (Semantic Search)\n"
        for i, res in enumerate(results, 1):
            context += f"{i}. {res['text']}\n"
        return context
