"""Vector store for semantic memory retrieval."""

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


class VectorStore:
    """Core memory store using vector embeddings (ChromaDB)."""

    def __init__(self, workspace_path: Path):
        self.workspace = workspace_path
        self.db_path = workspace_path / "brain" / "vector_db"
        self.collection = None
        
        if not HAS_CHROMA:
            logger.warning("ChromaDB not installed. Vector search will be disabled.")
            return
            
        try:
            # Initialize persistent client
            self.client = chromadb.PersistentClient(path=str(self.db_path))
            
            # Use default embedding function (all-MiniLM-L6-v2)
            # This downloads the model (~80MB) on first run
            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            
            self.collection = self.client.get_or_create_collection(
                name="memories",
                embedding_function=self.ef,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Vector store initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self.collection = None

    def add(self, text: str, metadata: dict[str, Any], doc_id: str | None = None) -> None:
        """Add a document to the vector store."""
        if not self.collection:
            return
            
        try:
            if not doc_id:
                doc_id = f"doc_{int(time.time()*1000)}_{hash(text)}"
            
            self.collection.add(
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            logger.debug(f"Added to vector store: {doc_id}")
        except Exception as e:
            logger.error(f"Vector add failed: {e}")

    def query(self, query_text: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        """
        Search for semantically similar documents.
        
        Returns list of dicts: {"text": str, "metadata": dict, "distance": float}
        """
        if not self.collection:
            return []
            
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where
            )
            
            output = []
            if not results["ids"]:
                return []
                
            for i in range(len(results["ids"][0])):
                output.append({
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    "id": results["ids"][0][i]
                })
            
            return output
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def count(self) -> int:
        """Count total documents."""
        if not self.collection:
            return 0
        return self.collection.count()
