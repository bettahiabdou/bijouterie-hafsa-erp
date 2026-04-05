"""
Shared utilities for AI image generation on products.
Used by both the management command (background batch) and views (manual trigger).
"""

import os
import logging
import requests as http_requests

from django.core.files.base import ContentFile
from django.utils import timezone

from .models import Product, ProductImage

logger = logging.getLogger(__name__)


def get_source_image(product):
    """Get the source image for AI generation. Returns ImageFieldFile or None."""
    if product.main_image:
        return product.main_image
    first_img = product.images.order_by('display_order').first()
    if first_img:
        return first_img.image
    return None


def generate_and_save_model_photo(product):
    """
    Generate an AI model photo for a single product and save it as a ProductImage.
    Returns the new ProductImage on success, raises on failure.
    """
    from ai_services.fal_client import enhance_product_image, image_file_to_data_uri

    source = get_source_image(product)
    if not source:
        raise Exception(f'No source image for product {product.reference}')

    image_url = image_file_to_data_uri(source.path)
    category_name = product.category.name if product.category else None

    result = enhance_product_image(image_url, category_name=category_name, mode='model')

    # Download the generated image
    img_response = http_requests.get(result['url'], timeout=30)
    img_response.raise_for_status()

    filename = f"model_{os.path.basename(source.name)}"
    if not filename.lower().endswith('.jpg'):
        filename = filename.rsplit('.', 1)[0] + '.jpg'

    new_img = ProductImage(product=product, display_order=99)
    new_img.image.save(filename, ContentFile(img_response.content), save=True)

    return new_img


def generate_batch(products):
    """
    Generate AI model photos for multiple products in parallel.
    Updates each product's ai_image_status accordingly.

    Returns dict of {product_id: ProductImage or Exception}.
    """
    from ai_services.fal_client import generate_model_photos_batch, image_file_to_data_uri

    # Build batch items
    items = []
    product_list = []
    for product in products:
        source = get_source_image(product)
        if not source:
            product.ai_image_status = Product.AIImageStatus.SKIPPED
            product.save(update_fields=['ai_image_status'])
            logger.info(f'Skipped {product.reference}: no source image')
            continue
        try:
            image_url = image_file_to_data_uri(source.path)
        except Exception as e:
            product.ai_image_status = Product.AIImageStatus.FAILED
            product.ai_image_error = f'Failed to read source image: {e}'
            product.ai_image_attempts += 1
            product.save(update_fields=['ai_image_status', 'ai_image_error', 'ai_image_attempts'])
            logger.error(f'Failed to read image for {product.reference}: {e}')
            continue

        category_name = product.category.name if product.category else None
        items.append((image_url, category_name))
        product_list.append((product, source))

    if not items:
        return {}

    # Submit all to fal.ai in parallel
    results = generate_model_photos_batch(items)

    output = {}
    for i, result in enumerate(results):
        product, source = product_list[i]
        try:
            if isinstance(result, Exception):
                raise result

            # Download and save the generated image
            img_response = http_requests.get(result['url'], timeout=30)
            img_response.raise_for_status()

            filename = f"model_{os.path.basename(source.name)}"
            if not filename.lower().endswith('.jpg'):
                filename = filename.rsplit('.', 1)[0] + '.jpg'

            new_img = ProductImage(product=product, display_order=99)
            new_img.image.save(filename, ContentFile(img_response.content), save=True)

            product.ai_image_status = Product.AIImageStatus.COMPLETED
            product.ai_image_error = None
            product.ai_image_completed_at = timezone.now()
            product.save(update_fields=['ai_image_status', 'ai_image_error', 'ai_image_completed_at'])

            output[product.id] = new_img
            logger.info(f'Generated AI image for {product.reference}')

        except Exception as e:
            product.ai_image_status = Product.AIImageStatus.FAILED
            product.ai_image_error = str(e)[:500]
            product.ai_image_attempts += 1
            product.save(update_fields=['ai_image_status', 'ai_image_error', 'ai_image_attempts'])

            output[product.id] = e
            logger.error(f'Failed AI image for {product.reference}: {e}')

    return output
