import hmac
import os
from fastapi import Header, HTTPException

def authorize(x_api_key: str = Header(default='')):
    expected = os.environ.get('API_KEY', '')
    if not expected:
        raise HTTPException(503, 'Set API_KEY before using the API')
    if not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(401, 'Invalid API key')
