"""
Product Image Enhancement for Bijouterie Hafsa ERP.

Uses Pillow for image enhancement and rembg for background removal.
Generates professional product photos with clean backgrounds.
"""

import io
import logging
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# Preset backgrounds (solid colors)
BACKGROUNDS = {
    'white': (255, 255, 255),
    'black': (20, 20, 20),
    'cream': (255, 253, 245),
    'gold': (248, 236, 194),
    'velvet': (60, 10, 30),
    'navy': (15, 23, 42),
}


def remove_background(image_bytes):
    """
    Remove background from an image using rembg.
    Returns RGBA PIL Image with transparent background.
    """
    try:
        from rembg import remove
        output_bytes = remove(image_bytes)
        return Image.open(io.BytesIO(output_bytes)).convert('RGBA')
    except ImportError:
        logger.error('rembg not installed. Run: pip install rembg[cpu]')
        raise
    except Exception as e:
        logger.error(f'Background removal failed: {e}')
        raise


def enhance_image(img, brightness=1.1, contrast=1.2, sharpness=1.3, color=1.1):
    """
    Enhance image quality: brightness, contrast, sharpness, color saturation.
    """
    if img.mode == 'RGBA':
        # Work on RGB copy, preserve alpha
        alpha = img.split()[-1]
        rgb = img.convert('RGB')
        rgb = ImageEnhance.Brightness(rgb).enhance(brightness)
        rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
        rgb = ImageEnhance.Sharpness(rgb).enhance(sharpness)
        rgb = ImageEnhance.Color(rgb).enhance(color)
        rgb = rgb.convert('RGBA')
        rgb.putalpha(alpha)
        return rgb
    else:
        img = ImageEnhance.Brightness(img).enhance(brightness)
        img = ImageEnhance.Contrast(img).enhance(contrast)
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
        img = ImageEnhance.Color(img).enhance(color)
        return img


def add_background(rgba_img, bg_color='white', output_size=(1200, 1200), padding=0.1):
    """
    Place a transparent image onto a solid background with padding.
    Centers the product in the frame.
    """
    if isinstance(bg_color, str):
        bg_color = BACKGROUNDS.get(bg_color, BACKGROUNDS['white'])

    bg = Image.new('RGB', output_size, bg_color)

    # Calculate padded area
    pad_px = int(min(output_size) * padding)
    available_w = output_size[0] - 2 * pad_px
    available_h = output_size[1] - 2 * pad_px

    # Resize product to fit within padded area, maintaining aspect ratio
    img_w, img_h = rgba_img.size
    ratio = min(available_w / img_w, available_h / img_h)
    new_w = int(img_w * ratio)
    new_h = int(img_h * ratio)
    resized = rgba_img.resize((new_w, new_h), Image.LANCZOS)

    # Center on background
    x = (output_size[0] - new_w) // 2
    y = (output_size[1] - new_h) // 2
    bg.paste(resized, (x, y), resized)

    return bg


def add_shadow(rgba_img, offset=(8, 8), blur_radius=15, shadow_color=(0, 0, 0, 80)):
    """
    Add a subtle drop shadow behind the product.
    """
    shadow = Image.new('RGBA', rgba_img.size, (0, 0, 0, 0))
    shadow_layer = Image.new('RGBA', rgba_img.size, shadow_color)
    shadow.paste(shadow_layer, mask=rgba_img.split()[-1])
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    # Offset shadow
    result = Image.new('RGBA', (
        rgba_img.size[0] + abs(offset[0]) + blur_radius * 2,
        rgba_img.size[1] + abs(offset[1]) + blur_radius * 2
    ), (0, 0, 0, 0))
    result.paste(shadow, (blur_radius + max(offset[0], 0), blur_radius + max(offset[1], 0)))
    result.paste(rgba_img, (blur_radius + max(-offset[0], 0), blur_radius + max(-offset[1], 0)), rgba_img)

    return result


def process_product_image(image_path_or_bytes, background='white', enhance=True, shadow=True):
    """
    Full pipeline: remove background → enhance → add shadow → place on background.

    Args:
        image_path_or_bytes: File path string or bytes
        background: Background color name or RGB tuple
        enhance: Apply image enhancement
        shadow: Add drop shadow

    Returns:
        PIL Image (RGB) ready to save
    """
    # Read image bytes
    if isinstance(image_path_or_bytes, (str, Path)):
        with open(image_path_or_bytes, 'rb') as f:
            image_bytes = f.read()
    else:
        image_bytes = image_path_or_bytes

    # Step 1: Remove background
    rgba = remove_background(image_bytes)

    # Step 2: Enhance
    if enhance:
        rgba = enhance_image(rgba)

    # Step 3: Add shadow
    if shadow:
        rgba = add_shadow(rgba)

    # Step 4: Place on background
    result = add_background(rgba, bg_color=background)

    return result


def save_enhanced_image(result_img, output_path):
    """Save the enhanced image as JPEG."""
    result_img.save(output_path, 'JPEG', quality=92, optimize=True)
    return output_path
