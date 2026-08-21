"""
RAG Predictive Risk Advisor
Uses a local Vector Database (ChromaDB) to store historical NPT events 
and query them to warn engineers about pad-specific geological/drilling risks.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

class PadRiskAdvisor:
    """
    Manages the ingestion and retrieval of historical pad-level drilling risks.
    Uses ChromaDB for local, air-gapped semantic search.
    """
    def __init__(self, persist_directory: str | Path = ".cache/rag_risk_db"):
        if not HAS_CHROMADB:
            logger.warning("ChromaDB not installed. RAG Risk Advisor disabled.")
            self.client = None
            return
            
        self.persist_dir = Path(persist_directory)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize local persistent client
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        
        # Get or create the collection for NPT history
        # Note: For production Russian semantic search, replace the default 
        # embedding function with a multilingual model like:
        # chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
        #     model_name="paraphrase-multilingual-MiniLM-L12-v2"
        # )
        self.collection = self.client.get_or_create_collection(
            name="gazprom_npt_history",
            metadata={"hnsw:space": "cosine"}
        )

    def ingest_well_npt(
        self, 
        pad_name: str, 
        well_name: str, 
        npt_events: list[dict], 
        current_depth_m: float | None = None
    ) -> int:
        """
        Ingest NPT events from a completed well into the vector database.
        Returns the number of events ingested.
        """
        if not self.client or not npt_events:
            return 0
            
        documents = []
        metadatas = []
        ids = []
        
        for i, event in enumerate(npt_events):
            desc = event.get("description", "Unknown NPT event")
            # Create a rich text document for the embedding
            doc_text = f"Pad {pad_name}, Well {well_name}: {desc}"
            
            documents.append(doc_text)
            metadatas.append({
                "pad_name": pad_name,
                "well_name": well_name,
                "npt_hours": float(event.get("duration_hrs") or 0),
                "depth_m": float(current_depth_m) if current_depth_m else 0.0,
                "severity": event.get("severity", "unknown"),
                "raw_text": desc[:500]
            })
            # Unique ID for the vector DB
            ids.append(f"{pad_name}_{well_name}_{i}")
            
        try:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Ingested {len(documents)} NPT events for {pad_name}/{well_name}")
            return len(documents)
        except Exception as exc:
            logger.error(f"Failed to ingest NPT events: {exc}")
            return 0

    def query_risks(
        self, 
        pad_name: str, 
        current_depth_m: float, 
        depth_tolerance_m: float = 500.0,
        n_results: int = 5
    ) -> list[dict[str, Any]]:
        """
        Query the vector DB for historical NPT events on the same pad 
        within a specific depth tolerance.
        """
        if not self.client:
            return []
            
        # We use a dummy query text, but filter heavily by metadata (pad and depth)
        # In a real semantic search, you'd query: "What went wrong at this depth?"
        query_text = f"Drilling risks and NPT events at {current_depth_m} meters"
        
        try:
            results = self.collection.query(
                query_texts=[query_text],
                where={
                    "$and": [
                        {"pad_name": {"$eq": pad_name}},
                        {"depth_m": {"$gte": current_depth_m - depth_tolerance_m}},
                        {"depth_m": {"$lte": current_depth_m + depth_tolerance_m}}
                    ]
                },
                n_results=n_results
            )
            
            warnings = []
            if results and results['metadatas'] and results['metadatas'][0]:
                for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
                    warnings.append({
                        "historical_well": meta.get("well_name"),
                        "historical_depth_m": meta.get("depth_m"),
                        "npt_hours": meta.get("npt_hours"),
                        "description": meta.get("raw_text"),
                        "similarity_score": round(1.0 - dist, 3) # Convert distance to similarity
                    })
            return warnings
            
        except Exception as exc:
            logger.error(f"RAG query failed: {exc}")
            return []