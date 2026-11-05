"""Input validation and permission rules; no Telegram or network dependency."""
import re
from urllib.parse import urlsplit

SELECTED = [1,4,6,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,24,25,26,27,28,30,31,32,33,34,35,36,37,38,40,42,43,44,46,47,48,49,50]
PERMISSIONS = {
    'owner': {'catalog', 'channels', 'admins', 'broadcast', 'stats', 'block', 'backup'},
    'manager': {'catalog', 'channels', 'broadcast', 'stats', 'block'},
    'editor': {'catalog'},
}
FIELDS = {
    'code': 'Kod', 'title': 'Nomi', 'kind': 'Turi (movie yoki series)',
    'genre': 'Janr', 'year': 'Yil', 'country': 'Davlat',
    'description': 'Tavsif', 'duration': 'Davomiylik (daqiqa)',
    'poster': 'Poster (rasm yuboring yoki HTTPS havola)',
    'trailer': 'Treyler HTTPS havolasi',
}
WIZARD = list(FIELDS)
OPTIONAL = {'genre', 'year', 'country', 'description', 'duration', 'poster', 'trailer'}

def allowed(role, permission):
    return permission in PERMISSIONS.get(role, set())

def code_value(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9_-]{1,32}', value):
        raise ValueError('Kod: 1–32 ta lotin harfi, raqam, _ yoki - bo‘lsin.')
    return value

def https_url(value):
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or len(value) > 500:
        raise ValueError('To‘liq HTTPS havola kiriting.')
    return value

def validate(field, value):
    value = value.strip()
    if field in OPTIONAL and value in ('-', '/skip', ''):
        return 0 if field in ('year', 'duration') else ''
    if field == 'code':
        return code_value(value)
    if field == 'kind':
        aliases = {'kino': 'movie', 'serial': 'series', 'movie': 'movie', 'series': 'series'}
        if value.lower() not in aliases:
            raise ValueError('movie (kino) yoki series (serial) yozing.')
        return aliases[value.lower()]
    if field in ('year', 'duration', 'season', 'episode'):
        if not value.isascii() or not value.isdigit():
            raise ValueError('Butun musbat son kiriting.')
        n = int(value)
        low, high = (1888, 2200) if field == 'year' else (1, 10000)
        if not low <= n <= high:
            raise ValueError(f'{low}–{high} oralig‘ida son kiriting.')
        return n
    if field in ('trailer', 'poster'):
        return https_url(value)
    max_len = {'title': 100, 'description': 450, 'genre': 40, 'country': 40,
               'language': 30, 'quality': 20}.get(field, 100)
    if not value or len(value) > max_len or '\n' in value and field != 'description':
        raise ValueError(f'1–{max_len} belgili matn kiriting.')
    return value

def parse_channel_caption(caption):
    """Explicit one-video-per-post format; never guesses metadata."""
    lines = (caption or '').splitlines()
    if not lines or lines[0].strip().lower() != '#kino':
        return None
    data = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        if ':' not in line:
            raise ValueError('Har satr field: value formatida bo‘lsin.')
        key, val = line.split(':', 1)
        key = key.strip().lower()
        if key not in set(FIELDS) | {'language', 'quality', 'season', 'episode'}:
            raise ValueError(f'Noma’lum maydon: {key}')
        if key in data:
            raise ValueError(f'Takroriy maydon: {key}')
        data[key] = validate(key, val)
    for key in ('code', 'title', 'kind', 'language', 'quality'):
        if key not in data:
            raise ValueError(f'Maydon yetishmayapti: {key}')
    for key in OPTIONAL:
        data.setdefault(key, 0 if key in ('year', 'duration') else '')
    if data['kind'] == 'series' and not all(data.get(k) for k in ('season', 'episode')):
        raise ValueError('Serial uchun season va episode kerak.')
    if data['kind'] == 'movie' and any(data.get(k) for k in ('season', 'episode')):
        raise ValueError('Kino uchun season va episode yozilmaydi.')
    data.setdefault('season', 0)
    data.setdefault('episode', 0)
    return data

def is_member(member):
    status = getattr(member.status, 'value', member.status)
    return status in ('creator', 'administrator', 'member') or (
        status == 'restricted' and bool(getattr(member, 'is_member', False)))
