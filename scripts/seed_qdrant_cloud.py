"""
Seed Qdrant Cloud Cluster with Canonical Invoice Schema Fields.

Connects to the cloud cluster specified by QDRANT_URL and QDRANT_API_KEY in .env,
initializes the collection (with dense and SPLADE sparse vector indexing),
and upserts the canonical invoice corpus.

Usage:
    python scripts/seed_qdrant_cloud.py [--recreate]
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from invoice_pipeline.universal.qdrant_setup import (
    CANONICAL_CORPUS,
    init_qdrant_collection,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_qdrant")


def get_embedding_models():
    """
    Attempts to load real fastembed and sentence_transformers models if installed;
    otherwise falls back gracefully.
    """
    dense_model = None
    sparse_model = None

    # Try loading dense model
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading dense model: paraphrase-multilingual-MiniLM-L12-v2 ...")
        dense_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("Dense model loaded successfully.")
    except Exception as e:
        logger.warning("sentence_transformers not loaded (%s). Checking fastembed for dense...", e)
        try:
            from fastembed import TextEmbedding
            dense_model = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            logger.info("Fastembed dense model loaded successfully.")
        except Exception as e2:
            logger.warning("Fastembed dense model not available (%s). Using fallback embeddings.", e2)

    # Try loading SPLADE sparse model
    try:
        from fastembed import SparseTextEmbedding
        logger.info("Loading SPLADE sparse model: prithivida/Splade_PP_en_v1 ...")
        sparse_model = SparseTextEmbedding(model_name="prithivida/Splade_PP_en_v1")
        logger.info("SPLADE sparse model loaded successfully.")
    except Exception as e:
        logger.warning("SPLADE sparse model not available (%s).", e)

    return dense_model, sparse_model


def main():
    parser = argparse.ArgumentParser(description="Seed Qdrant Cloud Cluster")
    parser.add_argument("--recreate", action="store_true", help="Force recreate collection if it exists")
    args = parser.parse_args()

    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    collection_name = os.getenv("QDRANT_COLLECTION_NAME", "invoice_schema_fields")

    if not url:
        logger.error("QDRANT_URL is not set in environment or .env file.")
        sys.exit(1)

    logger.info("Connecting to Qdrant Cloud at: %s", url)
    client = QdrantClient(url=url, api_key=api_key)

    collections = [c.name for c in client.get_collections().collections]
    logger.info("Existing collections on cluster: %s", collections)

    dense_model, sparse_model = get_embedding_models()

    logger.info("Initializing collection '%s' with %d canonical fields...", collection_name, len(CANONICAL_CORPUS))
    init_qdrant_collection(
        client=client,
        collection_name=collection_name,
        dense_dim=384,
        dense_model=dense_model,
        sparse_model=sparse_model,
        recreate=args.recreate,
    )

    info = client.get_collection(collection_name)
    logger.info("SUCCESS! Collection '%s' initialized on Qdrant Cloud.", collection_name)
    logger.info("Points count: %d, Status: %s", info.points_count, info.status)


if __name__ == "__main__":
    main()
