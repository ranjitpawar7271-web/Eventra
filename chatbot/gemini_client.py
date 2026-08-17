"""Minimal Gemini API client.

Deliberately a plain `requests` call to the REST endpoint rather than the
`google-generativeai` SDK — one extra dependency avoided, and the surface
area we actually use (send a prompt, get text back) doesn't need an SDK.

This is the ONLY place `settings.GEMINI_API_KEY` is read. The key never
reaches templates, JS, or API responses — callers here get back text or
an error code, nothing that could leak the key.
"""
import requests
from django.conf import settings

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Error codes returned instead of raising, so callers always get a clean
# (text, error) pair — matches the "AI API failure" case in the error
# handling requirements: never let this bubble up as a raw exception.
ERROR_NOT_CONFIGURED = 'not_configured'
ERROR_NETWORK = 'network_error'
ERROR_BAD_RESPONSE = 'bad_response'
ERROR_RATE_LIMITED = 'rate_limited'


def get_ai_response(system_prompt: str, user_message: str, timeout=15):
    """Returns (text, error). Exactly one of the two is set."""
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return None, ERROR_NOT_CONFIGURED

    model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash')
    url = GEMINI_ENDPOINT.format(model=model)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400},
    }

    try:
        response = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    except Exception:
        # Broad on purpose: any failure reaching the API (network error,
        # DNS, TLS, or an unexpected exception from the HTTP stack) must
        # degrade to the fallback path in services.py, never bubble up
        # as a raw 500 — matches the "AI API failure" error-handling
        # requirement.
        return None, ERROR_NETWORK

    if response.status_code == 429:
        return None, ERROR_RATE_LIMITED
    if response.status_code != 200:
        return None, ERROR_NETWORK

    try:
        data = response.json()
        text = data['candidates'][0]['content']['parts'][0]['text']
        return text.strip(), None
    except (KeyError, IndexError, ValueError, TypeError):
        return None, ERROR_BAD_RESPONSE
