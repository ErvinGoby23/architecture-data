from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pymongo import MongoClient
import pandas as pd

# ── CONFIG ──────────────────────────────────────────────
PG_URL    = 'postgresql://postgres:postgres@localhost:5432/postgres'
MONGO_URL = 'mongodb://localhost:27017'
MONGO_DB  = 'urban_data'

app = FastAPI(title="Urban Data Explorer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine(PG_URL)
mongo  = MongoClient(MONGO_URL)[MONGO_DB]

# ── ROUTES CONNECTIVITÉ ──────────────────────────────────

@app.get("/")
def root():
    return {"message": "Urban Data Explorer API", "version": "1.0.0"}

@app.get("/connectivite/score")
def get_score_connectivite(arrondissement: int = Query(None, description="ex: 75101")):
    """Score de connectivité global par arrondissement"""
    with engine.connect() as conn:
        if arrondissement:
            result = conn.execute(text("""
                SELECT * FROM gold.score_connectivite
                WHERE code_arrondissement = :arr
            """), {"arr": arrondissement})
        else:
            result = conn.execute(text("""
                SELECT * FROM gold.score_connectivite
                ORDER BY score_connectivite DESC
            """))
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows

@app.get("/connectivite/fibre")
def get_fibre(arrondissement: int = Query(None)):
    """Taux de couverture fibre par arrondissement"""
    with engine.connect() as conn:
        if arrondissement:
            result = conn.execute(text("""
                SELECT * FROM silver.fibre_paris
                WHERE code_arrondissement = :arr
            """), {"arr": arrondissement})
        else:
            result = conn.execute(text("""
                SELECT * FROM silver.fibre_paris
                ORDER BY taux_fibre_pct DESC
            """))
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows

@app.get("/connectivite/antennes")
def get_antennes(arrondissement: int = Query(None)):
    """Antennes agrégées par arrondissement"""
    with engine.connect() as conn:
        if arrondissement:
            result = conn.execute(text("""
                SELECT * FROM silver.antennes_paris
                WHERE code_arrondissement = :arr
            """), {"arr": arrondissement})
        else:
            result = conn.execute(text("""
                SELECT * FROM silver.antennes_paris
                ORDER BY nb_antennes DESC
            """))
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows

@app.get("/connectivite/antennes/detail")
def get_antennes_detail(
    arrondissement: int = Query(None),
    operateur: str = Query(None)
):
    """Détail de chaque antenne avec géométrie (MongoDB)"""
    query = {}
    if arrondissement:
        query["code_arrondissement"] = arrondissement
    if operateur:
        query["operateur"] = operateur.upper()

    docs = list(mongo["antennes_detail"].find(query, {"_id": 0}))
    if not docs:
        raise HTTPException(status_code=404, detail="Aucune antenne trouvée")
    return docs

@app.get("/connectivite/antennes/geojson")
def get_antennes_geojson(arrondissement: int = Query(None)):
    """Antennes au format GeoJSON pour la carte"""
    query = {}
    if arrondissement:
        query["code_arrondissement"] = arrondissement

    docs = list(mongo["antennes_detail"].find(query, {"_id": 0}))

    features = []
    for doc in docs:
        if doc.get("geo_shape"):
            features.append({
                "type": "Feature",
                "geometry": doc["geo_shape"],
                "properties": {
                    "code_site": doc.get("code_site"),
                    "adresse": doc.get("adresse"),
                    "operateur": doc.get("operateur"),
                    "type": doc.get("type"),
                    "code_arrondissement": doc.get("code_arrondissement")
                }
            })

    return {"type": "FeatureCollection", "features": features}