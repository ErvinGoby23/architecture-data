import os
from fastapi import HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from pymongo import MongoClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

PG_URL         = os.getenv("PG_URL")
PG_URL_REPLICA = os.getenv("PG_URL_REPLICA")
MONGO_URL      = os.getenv("MONGO_URL")
API_KEY        = os.getenv("API_KEY")

if not PG_URL:
    raise ValueError("PG_URL manquante dans le .env")
if not MONGO_URL:
    raise ValueError("MONGO_URL manquante dans le .env")
if not API_KEY:
    raise ValueError("API_KEY manquante dans le .env")

engine_primary = create_engine(PG_URL, pool_size=20, max_overflow=10)
engine_replica = create_engine(PG_URL_REPLICA, pool_size=20, max_overflow=10) if PG_URL_REPLICA else None

mongo   = MongoClient(MONGO_URL)
limiter = Limiter(key_func=get_remote_address)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def get_engine():
    try:
        with engine_primary.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine_primary
    except OperationalError:
        if engine_replica:
            return engine_replica
        raise

engine = engine_primary

def verify_api_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Clé API invalide")
    return key