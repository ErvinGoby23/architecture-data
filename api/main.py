"""
main.py — Urban Data Explorer API
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

PG_URL    = os.getenv("PG_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "urban_data")

app = FastAPI(title="Urban Data Explorer API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine(PG_URL)
mongo  = MongoClient(MONGO_URL)


@app.get("/")
def root():
    return {"message": "Urban Data Explorer API", "version": "2.0.0"}


# ── INDICATEUR 1 — MOBILITÉ ──────────────────────────────────────────────────

@app.get("/mobilite")
def get_mobilite(
    code_postal: Optional[int] = Query(None)
):
    with engine.connect() as conn:
        if code_postal:
            result = conn.execute(text(
                "SELECT * FROM gold.score_mobilite WHERE code_postal = :cp"
            ), {"cp": code_postal})
        else:
            result = conn.execute(text(
                "SELECT * FROM gold.score_mobilite ORDER BY rang"
            ))
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@app.get("/mobilite/points/geojson")
def get_mobilite_points_geojson(
    code_postal: Optional[int] = Query(None),
    type_point:  Optional[str] = Query(None)
):
    query = {}
    if code_postal:
        query["code_postal"] = code_postal
    if type_point:
        query["type"] = type_point

    docs = list(mongo["silver"]["indicateur_mobilite"].find(query, {"_id": 0}))

    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
            "code_postal": doc.get("code_postal"),
            "type":        doc.get("type"),
            "code_site":   doc.get("code_site"),
            "generation":  doc.get("generation"),
            "operateur":   doc.get("operateur"),
        }
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}


# ── INDICATEUR 2 — CONNECTIVITÉ ──────────────────────────────────────────────

@app.get("/connectivite")
def get_connectivite():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT * FROM gold.score_connectivite ORDER BY rang"
        ))
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@app.get("/connectivite/points/geojson")
def get_connectivite_points_geojson(
    code_postal: Optional[int] = Query(None)
):
    query = {}
    if code_postal:
        query["code_postal"] = code_postal

    docs = list(mongo["silver"]["indicateur_connectivite"].find(query, {"_id": 0}))

    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "code_postal": doc.get("code_postal"),
                "type":        doc.get("type"),
                "code_site":   doc.get("code_site"),
            }
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}



# exemple de date
# @router.get("/mobilite")
# @router.get("/mobilite")
# def get_mobilite(year: int = None):
#     query = "SELECT * FROM gold_mobilite"
#     if year:
#         query += f" WHERE EXTRACT(YEAR FROM date) = {year}"
#     ...