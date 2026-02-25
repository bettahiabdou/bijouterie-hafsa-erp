"""
Product embedding and semantic search using Scaleway embeddings API.
Supports French, Arabic (MSA), and Moroccan Darija queries.
"""

import json
import os
import logging
import math
from django.conf import settings
from . import scaleway_client

logger = logging.getLogger(__name__)

# Path to store product embeddings cache
EMBEDDINGS_CACHE_PATH = os.path.join(settings.BASE_DIR, 'ai_services', 'product_embeddings.json')


def _cosine_similarity(vec_a, vec_b):
    """Calculate cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def build_product_text(product):
    """
    Build a rich text representation of a product for embedding.
    Combines all searchable attributes.
    """
    parts = []

    if product.reference:
        parts.append(product.reference)
    if product.name:
        parts.append(product.name)
    if product.name_ar:
        parts.append(product.name_ar)
    if product.description:
        parts.append(product.description)
    if hasattr(product, 'category') and product.category:
        parts.append(product.category.name)
    if hasattr(product, 'metal_type') and product.metal_type:
        parts.append(product.metal_type.name)
    if hasattr(product, 'metal_purity') and product.metal_purity:
        parts.append(product.metal_purity.name)
    if product.barcode:
        parts.append(product.barcode)

    return ' | '.join(filter(None, parts))


def index_all_products(status_filter='available'):
    """
    Generate embeddings for all products and save to cache file.

    Args:
        status_filter: Only index products with this status (None = all)

    Returns:
        int: Number of products indexed
    """
    from products.models import Product

    if not scaleway_client.is_configured():
        logger.error('Scaleway AI not configured')
        return 0

    queryset = Product.objects.select_related('category', 'metal_type', 'metal_purity')
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    products = list(queryset)
    if not products:
        logger.info('No products to index')
        return 0

    # Build text representations
    texts = []
    product_ids = []
    for p in products:
        text = build_product_text(p)
        if text.strip():
            texts.append(text)
            product_ids.append(p.id)

    # Generate embeddings in batches (max 32 per request)
    all_embeddings = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        try:
            batch_embeddings = scaleway_client.get_embeddings(batch_texts)
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            logger.error(f'Embedding batch {i} failed: {e}')
            # Fill with None for failed batch
            all_embeddings.extend([None] * len(batch_texts))

    # Save to cache
    cache = {
        'product_ids': product_ids,
        'texts': texts,
        'embeddings': all_embeddings,
    }

    with open(EMBEDDINGS_CACHE_PATH, 'w') as f:
        json.dump(cache, f)

    indexed = sum(1 for e in all_embeddings if e is not None)
    logger.info(f'Indexed {indexed}/{len(products)} products')
    return indexed


def search_products(query, top_k=10, min_score=0.3):
    """
    Search products using semantic similarity.

    Args:
        query: Search query (French, Arabic, or Darija)
        top_k: Number of results to return
        min_score: Minimum similarity score (0-1)

    Returns:
        list: List of dicts [{"product_id": int, "score": float, "text": str}]
    """
    if not scaleway_client.is_configured():
        return []

    # Load cached embeddings
    if not os.path.exists(EMBEDDINGS_CACHE_PATH):
        logger.warning('Product embeddings not indexed yet. Run: python manage.py index_products')
        return []

    try:
        with open(EMBEDDINGS_CACHE_PATH, 'r') as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f'Failed to load embeddings cache: {e}')
        return []

    product_ids = cache.get('product_ids', [])
    texts = cache.get('texts', [])
    embeddings = cache.get('embeddings', [])

    if not embeddings:
        return []

    # Get query embedding
    try:
        query_embedding = scaleway_client.get_embeddings(query)[0]
    except Exception as e:
        logger.error(f'Failed to embed query: {e}')
        return []

    # Calculate similarities
    results = []
    for i, emb in enumerate(embeddings):
        if emb is None:
            continue
        score = _cosine_similarity(query_embedding, emb)
        if score >= min_score:
            results.append({
                'product_id': product_ids[i],
                'score': round(score, 4),
                'text': texts[i],
            })

    # Sort by score descending
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]
