"""
Video processing utilities for Bijouterie Hafsa ERP.

Uses the system `ffmpeg` / `ffprobe` binaries via subprocess so we avoid
adding a Python video dependency. iPhone HEVC .MOV files are transcoded
to MP4 (H.264 + AAC) with the moov atom moved to the start so browsers
can start playing while still downloading.

If ffmpeg is not installed on the server, falls back to saving the
original file so uploads don't error during provisioning.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile

from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

logger = logging.getLogger(__name__)

FFMPEG_BIN = shutil.which('ffmpeg')
FFPROBE_BIN = shutil.which('ffprobe')


def ffmpeg_available():
    return FFMPEG_BIN is not None


def _save_uploaded_to_temp(uploaded_file, suffix=''):
    """Persist an UploadedFile to a temp path so ffmpeg can read it."""
    fd, path = tempfile.mkstemp(suffix=suffix or os.path.splitext(uploaded_file.name)[1] or '.bin')
    try:
        with os.fdopen(fd, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
    except Exception:
        os.unlink(path)
        raise
    return path


def probe_video(path):
    """Return (duration_seconds, size_bytes). Falls back to size only when ffprobe is missing."""
    size = os.path.getsize(path) if os.path.exists(path) else None
    if not FFPROBE_BIN:
        return None, size
    try:
        result = subprocess.run(
            [
                FFPROBE_BIN, '-v', 'error', '-print_format', 'json',
                '-show_format', '-show_streams', path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout or '{}')
        duration = float(data.get('format', {}).get('duration', 0)) if data else 0
        return int(duration) if duration else None, size
    except Exception as exc:
        logger.warning(f'ffprobe failed for {path}: {exc}')
        return None, size


def convert_video_to_mp4(uploaded_file):
    """
    Transcode any video to a browser-friendly MP4 (H.264 + AAC) and return
    a Django-compatible file-like object plus an extracted poster image.

    Returns a dict:
        {
            'video': <File-like ready to assign to FileField>,
            'video_name': 'foo.mp4',
            'poster': <File-like or None>,
            'poster_name': 'foo.jpg' or None,
            'duration': int seconds or None,
            'size': int bytes,
            'converted': True/False (False = saved original, ffmpeg missing/failed),
        }
    """
    original_name = uploaded_file.name
    base_name = os.path.splitext(os.path.basename(original_name))[0]

    # Always copy upload to a temp file so we can probe/transcode
    input_path = _save_uploaded_to_temp(uploaded_file)

    output_dir = tempfile.mkdtemp(prefix='hafsa_video_')
    output_path = os.path.join(output_dir, f'{base_name}.mp4')
    poster_path = os.path.join(output_dir, f'{base_name}.jpg')

    converted = False
    if FFMPEG_BIN:
        try:
            cmd = [
                FFMPEG_BIN, '-y', '-i', input_path,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0 and os.path.exists(output_path):
                converted = True
            else:
                logger.warning(
                    f'ffmpeg conversion failed for {original_name} '
                    f'(rc={result.returncode}): {result.stderr[-500:] if result.stderr else ""}'
                )
        except Exception as exc:
            logger.warning(f'ffmpeg conversion error for {original_name}: {exc}')
    else:
        logger.warning('ffmpeg binary not found on PATH — saving original video without conversion')

    # Try to extract a poster frame at 1 second (or 0 if the video is shorter)
    if FFMPEG_BIN:
        try:
            subprocess.run(
                [FFMPEG_BIN, '-y', '-i', output_path if converted else input_path,
                 '-ss', '00:00:01', '-vframes', '1', '-q:v', '2', poster_path],
                capture_output=True, timeout=30,
            )
            if not os.path.exists(poster_path):
                # Retry at 0s for very short clips
                subprocess.run(
                    [FFMPEG_BIN, '-y', '-i', output_path if converted else input_path,
                     '-ss', '0', '-vframes', '1', '-q:v', '2', poster_path],
                    capture_output=True, timeout=30,
                )
        except Exception as exc:
            logger.warning(f'Poster extraction failed for {original_name}: {exc}')

    # Build outputs
    if converted:
        final_path = output_path
        final_name = f'{base_name}.mp4'
    else:
        final_path = input_path
        final_name = original_name

    duration, size = probe_video(final_path)

    # Read the final video into a Django InMemoryUploadedFile (acceptable up
    # to FILE_UPLOAD_MAX_MEMORY_SIZE; for larger files, Django will spool to disk).
    with open(final_path, 'rb') as f:
        video_bytes = f.read()

    from io import BytesIO
    video_file = InMemoryUploadedFile(
        file=BytesIO(video_bytes),
        field_name='video',
        name=final_name,
        content_type='video/mp4' if converted else (uploaded_file.content_type or 'application/octet-stream'),
        size=len(video_bytes),
        charset=None,
    )

    poster_file = None
    poster_name = None
    if os.path.exists(poster_path):
        with open(poster_path, 'rb') as f:
            poster_bytes = f.read()
        poster_name = f'{base_name}.jpg'
        poster_file = InMemoryUploadedFile(
            file=BytesIO(poster_bytes),
            field_name='poster',
            name=poster_name,
            content_type='image/jpeg',
            size=len(poster_bytes),
            charset=None,
        )

    # Cleanup temp files
    try:
        if os.path.exists(input_path):
            os.unlink(input_path)
        if os.path.exists(output_path) and output_path != final_path:
            os.unlink(output_path)
        if os.path.exists(poster_path):
            os.unlink(poster_path)
        shutil.rmtree(output_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        'video': video_file,
        'video_name': final_name,
        'poster': poster_file,
        'poster_name': poster_name,
        'duration': duration,
        'size': size or len(video_bytes),
        'converted': converted,
    }
