"""
Scaleway Generative APIs client for Bijouterie Hafsa ERP.
OpenAI-compatible API with vision, chat, embeddings, and audio support.
"""

import os
import json
import base64
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Default configuration
SCALEWAY_API_KEY = os.getenv('SCALEWAY_AI_API_KEY', '')
SCALEWAY_BASE_URL = os.getenv(
    'SCALEWAY_AI_BASE_URL',
    'https://api.scaleway.ai/v1'
)

# Model aliases for convenience
MODELS = {
    'vision': 'pixtral-12b-2409',
    'vision_large': 'gemma-3-27b-it',
    'chat': 'gpt-oss-120b',
    'chat_large': 'qwen3-235b-a22b-instruct-2507',
    'embedding': 'bge-multilingual-gemma2',
    'whisper': 'whisper-large-v3',
    'voice_chat': 'voxtral-small-24b-2507',
}


def _get_headers():
    """Get API headers with authentication."""
    return {
        'Authorization': f'Bearer {SCALEWAY_API_KEY}',
        'Content-Type': 'application/json',
    }


def chat_completion(messages, model=None, temperature=0.3, max_tokens=1024,
                    response_format=None, **kwargs):
    """
    Send a chat completion request to Scaleway API.

    Args:
        messages: List of message dicts [{"role": "user", "content": "..."}]
        model: Model name (default: gpt-oss-120b)
        temperature: Creativity (0-1)
        max_tokens: Max response length
        response_format: Optional {"type": "json_object"} for JSON mode

    Returns:
        str: The assistant's response text
    """
    model = model or MODELS['chat']

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    if response_format:
        payload['response_format'] = response_format

    try:
        response = requests.post(
            f'{SCALEWAY_BASE_URL}/chat/completions',
            headers=_get_headers(),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        logger.error(f'Scaleway chat API error: {e}')
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f'Response: {e.response.text}')
        raise


def vision_completion(image_data, prompt, model=None, temperature=0.2,
                      max_tokens=2048, response_format=None):
    """
    Send an image + text prompt to a vision model.

    Args:
        image_data: Either base64 string, bytes, or file path
        prompt: Text prompt describing what to extract
        model: Vision model (default: pixtral-12b-2409)
        temperature: Creativity (0-1)
        max_tokens: Max response length
        response_format: Optional {"type": "json_object"} for JSON mode

    Returns:
        str: The model's response text
    """
    model = model or MODELS['vision']

    # Convert image to base64 if needed
    if isinstance(image_data, bytes):
        b64 = base64.b64encode(image_data).decode('utf-8')
    elif isinstance(image_data, str) and os.path.isfile(image_data):
        with open(image_data, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
    else:
        # Assume already base64
        b64 = image_data

    # Detect image type
    image_url = f'data:image/jpeg;base64,{b64}'

    messages = [
        {
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {'url': image_url}
                },
                {
                    'type': 'text',
                    'text': prompt
                }
            ]
        }
    ]

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    if response_format:
        payload['response_format'] = response_format

    try:
        response = requests.post(
            f'{SCALEWAY_BASE_URL}/chat/completions',
            headers=_get_headers(),
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        logger.error(f'Scaleway vision API error: {e}')
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f'Response: {e.response.text}')
        raise


def get_embeddings(texts, model=None):
    """
    Get text embeddings from Scaleway API.

    Args:
        texts: Single string or list of strings
        model: Embedding model (default: bge-multilingual-gemma2)

    Returns:
        list: List of embedding vectors (list of floats)
    """
    model = model or MODELS['embedding']

    if isinstance(texts, str):
        texts = [texts]

    payload = {
        'model': model,
        'input': texts,
    }

    try:
        response = requests.post(
            f'{SCALEWAY_BASE_URL}/embeddings',
            headers=_get_headers(),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return [item['embedding'] for item in data['data']]
    except requests.exceptions.RequestException as e:
        logger.error(f'Scaleway embedding API error: {e}')
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f'Response: {e.response.text}')
        raise


def transcribe_audio(audio_data, filename='audio.ogg'):
    """
    Transcribe audio using Whisper via Scaleway API.

    Args:
        audio_data: Audio file bytes
        filename: Original filename for content type detection

    Returns:
        str: Transcribed text
    """
    model = MODELS['whisper']

    try:
        headers = {
            'Authorization': f'Bearer {SCALEWAY_API_KEY}',
        }
        files = {
            'file': (filename, audio_data),
        }
        data = {
            'model': model,
        }

        response = requests.post(
            f'{SCALEWAY_BASE_URL}/audio/transcriptions',
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        return result.get('text', '')
    except requests.exceptions.RequestException as e:
        logger.error(f'Scaleway Whisper API error: {e}')
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f'Response: {e.response.text}')
        raise


def is_configured():
    """Check if Scaleway API is properly configured."""
    return bool(SCALEWAY_API_KEY)
