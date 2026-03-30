"""
Fal.ai client for Bijouterie Hafsa ERP.
Handles image enhancement: background removal (BiRefNet) and
product-on-model generation (FLUX Kontext).
"""

import os
import io
import base64
import logging
import requests
from PIL import Image

logger = logging.getLogger(__name__)

FAL_API_KEY = os.getenv('FAL_AI_KEY', '')
FAL_QUEUE_URL = 'https://queue.fal.run'

# Category → prompt mapping for jewelry-on-model generation
CATEGORY_PROMPTS = {
    # Necklaces / Chains
    'collier': "This elegant gold necklace worn on a beautiful woman's neck, close-up shot, soft studio lighting, luxury jewelry photography, dark background",
    'chaine': "This delicate gold chain worn on a woman's neck, close-up shot, soft studio lighting, luxury jewelry photography, dark background",
    'sautoir': "This long gold sautoir necklace worn on a woman's neck and chest, close-up shot, studio lighting, luxury jewelry photography",
    # Bracelets
    'bracelet': "This gold bracelet worn on a woman's wrist, close-up shot of the hand and wrist, studio lighting, luxury jewelry photography, dark background",
    'gourmette': "This gold gourmette chain bracelet worn on a woman's wrist, close-up shot, studio lighting, luxury jewelry photography",
    # Bangles
    'demlij': "These traditional Moroccan gold bangles worn on a woman's wrist, close-up shot showing multiple bangles stacked, studio lighting, luxury jewelry photography",
    # Rings
    'bague': "This gold ring worn on a woman's finger, close-up shot of the hand, soft studio lighting, luxury jewelry photography, dark background",
    'alliance': "This gold wedding ring worn on a woman's ring finger, close-up shot, romantic studio lighting, luxury jewelry photography",
    # Earrings
    'boucle': "These gold earrings worn on a woman's ear, close-up side profile shot, studio lighting, luxury jewelry photography, dark background",
    "boucles d'oreilles": "These gold earrings worn on a woman's ear, close-up side profile shot, studio lighting, luxury jewelry photography",
    # Pendants
    'pendentif': "This gold pendant hanging on a woman's neck on a fine chain, close-up shot, studio lighting, luxury jewelry photography, dark background",
    # Belts
    'sertla': "This traditional Moroccan gold belt (sertla) worn on a woman's waist over fabric, close-up shot, studio lighting, luxury jewelry photography",
    'ceinture': "This ornate gold belt worn on a woman's waist, close-up shot, studio lighting, luxury jewelry photography",
    # Headpieces
    'madmma': "This traditional Moroccan gold headpiece (madmma) worn on a woman's forehead, close-up portrait shot, studio lighting, luxury jewelry photography",
    'tawss': "This traditional gold headpiece worn on a woman's head, close-up shot, studio lighting, luxury jewelry photography",
    # Sets
    'ensemble': "This complete gold jewelry set (necklace, bracelet, earrings) elegantly displayed on a woman, medium shot, studio lighting, luxury jewelry photography",
    'parure': "This matching gold jewelry set worn by a woman, showing necklace and earrings, studio lighting, luxury jewelry photography",
    # Brooches
    'broche': "This gold brooch pinned on dark fabric on a woman's chest, close-up shot, studio lighting, luxury jewelry photography",
    # Default
    'default': "This gold jewelry piece displayed in a professional studio setting, close-up shot, soft lighting, luxury jewelry photography, dark background",
}


def is_configured():
    return bool(FAL_API_KEY)


def image_file_to_data_uri(file_path):
    """Convert a local image file to a base64 data URI for fal.ai."""
    with open(file_path, 'rb') as f:
        data = f.read()

    # Convert HEIC to JPEG since fal.ai may not support HEIC
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ('.heic', '.heif'):
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'JPEG', quality=90)
        data = buf.getvalue()
        mime = 'image/jpeg'
    else:
        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
        mime = mime_map.get(ext, 'image/jpeg')

    b64 = base64.b64encode(data).decode('utf-8')
    return f'data:{mime};base64,{b64}'


def _get_headers():
    return {
        'Authorization': f'Key {FAL_API_KEY}',
        'Content-Type': 'application/json',
    }


def _submit_and_poll(endpoint, payload, timeout=180):
    """Submit a job to fal.ai queue and poll until complete."""
    import time

    # Submit to queue
    response = requests.post(
        f'{FAL_QUEUE_URL}/{endpoint}',
        headers=_get_headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    response_url = data.get('response_url')
    status_url = data.get('status_url')

    if not response_url:
        raise Exception(f'No response_url from fal.ai: {data}')

    # Poll for result
    start = time.time()
    while time.time() - start < timeout:
        status_resp = requests.get(status_url, headers=_get_headers(), timeout=15)
        status_data = status_resp.json()
        status = status_data.get('status')

        if status == 'COMPLETED':
            # Fetch the actual result
            result_resp = requests.get(response_url, headers=_get_headers(), timeout=30)
            result_resp.raise_for_status()
            return result_resp.json()
        elif status in ('FAILED', 'CANCELLED'):
            raise Exception(f'Fal.ai job {status}: {status_data}')

        time.sleep(3)

    raise Exception(f'Fal.ai job timed out after {timeout}s')


def _get_category_prompt(category_name):
    """Match category name to the best prompt."""
    if not category_name:
        return CATEGORY_PROMPTS['default']

    name_lower = category_name.lower().strip()

    # Exact match first
    if name_lower in CATEGORY_PROMPTS:
        return CATEGORY_PROMPTS[name_lower]

    # Partial match
    for key, prompt in CATEGORY_PROMPTS.items():
        if key in name_lower or name_lower in key:
            return prompt

    return CATEGORY_PROMPTS['default']


def remove_background(image_url):
    """
    Remove background using BiRefNet on fal.ai.
    Returns the URL of the processed image.
    """
    data = _submit_and_poll('fal-ai/birefnet', {
        'image_url': image_url,
        'model': 'General Use (Heavy)',
        'operating_resolution': '1024x1024',
        'output_format': 'png',
    }, timeout=120)
    return data['image']['url']


def generate_model_photo(image_url, category_name=None, custom_prompt=None):
    """
    Generate a product-on-model photo using FLUX Kontext.
    Takes the product image and generates it worn by a model.
    """
    prompt = custom_prompt or _get_category_prompt(category_name)

    data = _submit_and_poll('fal-ai/flux-pro/kontext', {
        'image_url': image_url,
        'prompt': prompt,
        'num_images': 1,
        'output_format': 'jpeg',
        'guidance_scale': 3.5,
        'aspect_ratio': '1:1',
    }, timeout=180)

    if data.get('images') and len(data['images']) > 0:
        return data['images'][0]

    raise Exception(f'No image returned from fal.ai: {data}')


def enhance_product_image(image_url, category_name=None, mode='background', background='white', custom_prompt=None):
    """
    Main entry point for image enhancement.

    Args:
        image_url: Public URL of the product image
        category_name: Product category name
        mode: 'background' (remove bg + solid color) or 'model' (on-model photo)
        background: Background color for 'background' mode
        custom_prompt: Custom prompt for 'model' mode

    Returns:
        dict with 'url' and metadata
    """
    if not is_configured():
        raise Exception('Fal.ai API key not configured (FAL_AI_KEY)')

    if mode == 'model':
        result = generate_model_photo(image_url, category_name, custom_prompt)
        return {
            'url': result['url'],
            'width': result.get('width', 1024),
            'height': result.get('height', 1024),
            'mode': 'model',
        }
    else:
        # Background removal with BiRefNet
        result_url = remove_background(image_url)
        return {
            'url': result_url,
            'mode': 'background',
        }
