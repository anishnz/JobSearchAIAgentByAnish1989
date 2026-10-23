"""Encrypt saved passwords and API keys (Gmail app passwords, Claude keys) in the database.

The encryption key comes from DJANGO_SECRET_KEY in .env. If that value changes,
saved keys can no longer be read and must be entered again.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    digest = hashlib.sha256(("jobsearch-agent:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def mask(value):
    return (value[:10] + "..." + value[-4:]) if value and len(value) > 16 else ("saved" if value else "")
