import os
from fastapi import HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import create_engine
from pymongo import MongoClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

PG_URL    = os.getenv("PG_URL")
MONGO_URL = os.getenv("MONGO_URL")
API_KEY   = os.getenv("API_KEY")

if not PG_URL:
    raise ValueError("PG_URL manquante dans le .env")
if not MONGO_URL:
    raise ValueError("MONGO_URL manquante dans le .env")
if not API_KEY:
    raise ValueError("API_KEY manquante dans le .env")

engine = create_engine(PG_URL)
mongo  = MongoClient(MONGO_URL)
limiter = Limiter(key_func=get_remote_address)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Clé API invalide")
    return key