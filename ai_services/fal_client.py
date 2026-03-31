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

# Moroccan cultural context for all prompts
_MOROCCAN_STYLE = "elegant Moroccan woman with olive skin, wearing modest dark caftan with high neckline"
_PHOTO_STYLE = "professional luxury jewelry e-commerce photography, sharp focus on the jewelry, soft warm studio lighting, dark gradient background, 4K detail"

# Category → prompt mapping for jewelry-on-model generation
# Rules: preserve EXACT jewelry piece, no extra accessories, Moroccan modest styling
CATEGORY_PROMPTS = {
    # Necklaces / Chains
    'collier': f"Place this exact gold necklace around the neck of an {_MOROCCAN_STYLE}. Show ONLY this one necklace, absolutely no other jewelry, no earrings, no bracelets. Tight close-up of neck and upper chest area. {_PHOTO_STYLE}",
    'chaine': f"Place this exact gold chain around the neck of an {_MOROCCAN_STYLE}. Show ONLY this one chain, no other jewelry at all. Close-up of neck area. {_PHOTO_STYLE}",
    'sautoir': f"Place this exact long gold necklace on an {_MOROCCAN_STYLE}, hanging to mid-chest. Show ONLY this necklace, no other jewelry. Close-up shot from chin to chest. {_PHOTO_STYLE}",
    # Bracelets
    'bracelet': f"Place this exact gold bracelet on the wrist of an {_MOROCCAN_STYLE}. Show ONLY this bracelet, no rings, no other jewelry. Tight close-up of wrist and hand with henna-style elegance. {_PHOTO_STYLE}",
    'gourmette': f"Place this exact gold chain bracelet on the wrist of an {_MOROCCAN_STYLE}. Show ONLY this bracelet, no other jewelry. Close-up of wrist. {_PHOTO_STYLE}",
    # Bangles
    'demlij': f"Place these exact gold bangles stacked on the wrist of an {_MOROCCAN_STYLE}. Show ONLY these bangles, no other jewelry. Close-up of wrist showing the stack. {_PHOTO_STYLE}",
    # Rings
    'bague': f"Place this exact gold ring on the finger of an {_MOROCCAN_STYLE}. Show ONLY this ring, no other rings or jewelry. Tight close-up of hand and fingers. {_PHOTO_STYLE}",
    'alliance': f"Place this exact gold wedding ring on the ring finger of an {_MOROCCAN_STYLE}. Show ONLY this ring, no other jewelry. Close-up of hand. {_PHOTO_STYLE}",
    # Earrings
    'boucle': f"Place these exact gold earrings on the ear of an {_MOROCCAN_STYLE} wearing a hijab that frames the face showing the ears. Show ONLY these earrings, no necklace, no other jewelry. Close-up side profile. {_PHOTO_STYLE}",
    "boucles d'oreilles": f"Place these exact gold earrings on the ear of an {_MOROCCAN_STYLE} wearing a hijab that frames the face showing the ears. Show ONLY these earrings, no other jewelry. Close-up side profile. {_PHOTO_STYLE}",
    # Pendants
    'pendentif': f"Place this exact gold pendant on a chain around the neck of an {_MOROCCAN_STYLE}. Show ONLY this pendant, no earrings, no other jewelry. Close-up of neck and pendant. {_PHOTO_STYLE}",
    # Belts
    'sertla': f"Place this exact traditional Moroccan gold belt (sertla) around the waist of an {_MOROCCAN_STYLE} wearing an embroidered caftan. Show ONLY this belt. Medium close-up of waist area. {_PHOTO_STYLE}",
    'ceinture': f"Place this exact ornate gold belt around the waist of an {_MOROCCAN_STYLE} wearing a caftan. Show ONLY this belt, no other jewelry. Close-up of waist. {_PHOTO_STYLE}",
    # Headpieces
    'madmma': f"Place this exact traditional Moroccan gold headpiece (tama/madmma) on the forehead of an {_MOROCCAN_STYLE} wearing traditional Moroccan bridal attire with head covering. Show ONLY this headpiece. Close-up portrait. {_PHOTO_STYLE}",
    'tawss': f"Place this exact gold headpiece on the head of an {_MOROCCAN_STYLE} wearing traditional Moroccan attire. Show ONLY this headpiece, no other jewelry. Close-up portrait. {_PHOTO_STYLE}",
    # Sets
    'ensemble': f"Place this exact complete gold jewelry set on an {_MOROCCAN_STYLE} wearing traditional Moroccan bridal caftan. Show all pieces of the set together. Medium shot. {_PHOTO_STYLE}",
    'parure': f"Place this exact matching gold jewelry set on an {_MOROCCAN_STYLE} wearing a caftan. Show all matching pieces. Medium shot. {_PHOTO_STYLE}",
    # Brooches
    'broche': f"Place this exact gold brooch pinned on the chest area of an {_MOROCCAN_STYLE}. Show ONLY this brooch, no other jewelry. Close-up of chest area. {_PHOTO_STYLE}",
    # Default
    'default': f"Place this exact gold jewelry piece on an {_MOROCCAN_STYLE} in the appropriate body position. Show ONLY this piece, no other jewelry. Close-up, {_PHOTO_STYLE}",
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
        'guidance_scale': 7.0,
        'num_inference_steps': 28,
        'aspect_ratio': '3:4',
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
