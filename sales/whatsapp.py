"""
WhatsApp Cloud API client (Meta Graph API) for Bijouterie Hafsa.

Used to post return-reception notifications (photo + info) into a WhatsApp
group via the Groups API. All configuration comes from environment variables
so no secret ever lives in the codebase:

    WHATSAPP_ENABLED           "true" to actually send (default false)
    WHATSAPP_TOKEN             permanent access token (System User token)
    WHATSAPP_PHONE_NUMBER_ID   the business phone number id
    WHATSAPP_RETOUR_GROUP_ID   group id of the "retour" group
    WHATSAPP_API_VERSION       Graph API version (default v25.0)

Requires an Official Business Account. Groups are capped at 8 participants.
Every send is best-effort: failures are logged and never raised to the caller.
"""
import os
import logging

import requests

logger = logging.getLogger(__name__)

GRAPH = 'https://graph.facebook.com'


def _env_cfg():
    return {
        'enabled': os.getenv('WHATSAPP_ENABLED', 'false').lower() == 'true',
        'token': os.getenv('WHATSAPP_TOKEN', '').strip(),
        'phone_id': os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip(),
        'group_id': os.getenv('WHATSAPP_RETOUR_GROUP_ID', '').strip(),
        'version': os.getenv('WHATSAPP_API_VERSION', 'v25.0').strip(),
    }


def _cfg():
    """Merge DB config (admin UI) over environment variables. A non-empty DB
    field wins; empty DB fields fall back to the WHATSAPP_* env vars."""
    env = _env_cfg()
    try:
        from sales.models import WhatsAppConfig
        db = WhatsAppConfig.get_solo()
    except Exception:
        db = None
    if db is None:
        return env
    def pick(dbv, envv):
        dbv = (dbv or '').strip()
        return dbv if dbv else envv
    return {
        'enabled': bool(db.enabled) or env['enabled'],
        'token': pick(db.token, env['token']),
        'phone_id': pick(db.phone_number_id, env['phone_id']),
        'group_id': pick(db.retour_group_id, env['group_id']),
        'version': pick(db.api_version, env['version']) or 'v25.0',
    }


def is_configured():
    c = _cfg()
    return bool(c['token'] and c['phone_id'])


def _headers(c):
    return {'Authorization': f"Bearer {c['token']}", 'Content-Type': 'application/json'}


def _messages_url(c):
    return f"{GRAPH}/{c['version']}/{c['phone_id']}/messages"


def _groups_url(c):
    return f"{GRAPH}/{c['version']}/{c['phone_id']}/groups"


# ---------------------------------------------------------------------------
# Group management (used once, via the whatsapp_group management command)
# ---------------------------------------------------------------------------

def create_group(subject, participants):
    """Create a WhatsApp group. `participants` is a list of E.164 numbers
    (digits only, no '+'). Returns the parsed JSON (contains the group id)."""
    c = _cfg()
    if not is_configured():
        return {'error': 'WhatsApp not configured (WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID).'}
    payload = {
        'messaging_product': 'whatsapp',
        'subject': subject,
        'participants': [{'user': str(p).strip()} for p in participants if str(p).strip()],
    }
    r = requests.post(_groups_url(c), headers=_headers(c), json=payload, timeout=25)
    try:
        return r.json()
    except ValueError:
        return {'status_code': r.status_code, 'text': r.text}


def get_phone_info():
    """Diagnostic: fetch the business number's status incl. OBA flags."""
    c = _cfg()
    if not is_configured():
        return {'error': 'WhatsApp not configured.'}
    url = f"{GRAPH}/{c['version']}/{c['phone_id']}"
    fields = ('id,display_phone_number,verified_name,code_verification_status,'
              'quality_rating,platform_type,is_official_business_account,'
              'name_status,messaging_limit_tier,whatsapp_business_api_data')
    try:
        r = requests.get(url, headers=_headers(c), params={'fields': fields}, timeout=25)
        return r.json() if r.content else {'status_code': r.status_code}
    except Exception as e:
        return {'error': str(e)}


def get_group(group_id):
    """Fetch group info (includes invite link when available)."""
    c = _cfg()
    if not is_configured():
        return {'error': 'WhatsApp not configured.'}
    url = f"{GRAPH}/{c['version']}/{group_id}"
    r = requests.get(url, headers=_headers(c), timeout=25)
    try:
        return r.json()
    except ValueError:
        return {'status_code': r.status_code, 'text': r.text}


# ---------------------------------------------------------------------------
# Media upload (so we never have to expose /media/ publicly)
# ---------------------------------------------------------------------------

def upload_media(file_path, mime='image/jpeg'):
    """Upload a local file to WhatsApp; returns the media id (or None)."""
    c = _cfg()
    if not is_configured():
        return None
    url = f"{GRAPH}/{c['version']}/{c['phone_id']}/media"
    try:
        with open(file_path, 'rb') as fh:
            files = {'file': (os.path.basename(file_path), fh, mime)}
            data = {'messaging_product': 'whatsapp', 'type': mime}
            r = requests.post(
                url, headers={'Authorization': f"Bearer {c['token']}"},
                data=data, files=files, timeout=40)
        j = r.json() if r.content else {}
        if r.status_code >= 400:
            logger.warning('WhatsApp media upload failed (%s): %s', r.status_code, j)
        return j.get('id')
    except Exception as e:
        logger.warning('WhatsApp media upload error: %s', e)
        return None


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_group_image(caption, media_id=None, image_url=None, group_id=None):
    """Post an image with a caption into the retour group. Prefer media_id
    (uploaded file); fall back to a public image_url. No-op unless enabled +
    configured + a group id is set."""
    c = _cfg()
    gid = (group_id or c['group_id']).strip()
    if not c['enabled']:
        return {'skipped': 'disabled'}
    if not is_configured():
        return {'skipped': 'not_configured'}
    if not gid:
        return {'skipped': 'no_group_id'}
    if media_id:
        img = {'id': media_id, 'caption': caption[:1024]}
    elif image_url:
        img = {'link': image_url, 'caption': caption[:1024]}
    else:
        return {'skipped': 'no_image'}
    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'group',
        'to': gid,
        'type': 'image',
        'image': img,
    }
    try:
        r = requests.post(_messages_url(c), headers=_headers(c), json=payload, timeout=25)
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            logger.warning('WhatsApp send failed (%s): %s', r.status_code, data)
        return data
    except Exception as e:  # never break the caller
        logger.warning('WhatsApp send error: %s', e)
        return {'error': str(e)}


def send_group_text(body, group_id=None):
    """Post a plain text message into the retour group."""
    c = _cfg()
    gid = (group_id or c['group_id']).strip()
    if not c['enabled'] or not is_configured() or not gid:
        return {'skipped': True}
    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'group',
        'to': gid,
        'type': 'text',
        'text': {'preview_url': False, 'body': body[:4096]},
    }
    try:
        r = requests.post(_messages_url(c), headers=_headers(c), json=payload, timeout=25)
        return r.json() if r.content else {}
    except Exception as e:
        logger.warning('WhatsApp text send error: %s', e)
        return {'error': str(e)}
