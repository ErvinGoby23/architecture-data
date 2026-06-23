from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/connectivite", tags=["Connectivité"])


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS
# --------------------------------------------------------------------------

@router.get("")
@limiter.limit("60/minute")
def get_connectivite(
    request: Request,
    code_postal: Optional[int] = Query(None),
    _: str = Depends(verify_api_key),
):
    """Score de connectivité par arrondissement."""
    with get_engine().connect() as conn:
        if code_postal:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite WHERE code_postal = :cp"),
                {"cp": code_postal},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@router.get("/quartier")
@limiter.limit("60/minute")
def get_connectivite_quartier(
    request: Request,
    code_quartier:  Optional[int] = Query(None),
    arrondissement: Optional[int] = Query(None),
    _: str = Depends(verify_api_key),
):
    """Score de connectivité par quartier (80 quartiers). Filtrable par arrondissement."""
    with get_engine().connect() as conn:
        if code_quartier:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite_quartier WHERE code_quartier = :cq"),
                {"cq": code_quartier},
            )
        elif arrondissement:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite_quartier WHERE arrondissement = :arr ORDER BY rang"),
                {"arr": arrondissement},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite_quartier ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Quartier non trouvé")
    return rows


# --------------------------------------------------------------------------
# POINTS GÉOSPATIAUX GEOJSON
# --------------------------------------------------------------------------

@router.get("/points/geojson")
@limiter.limit("30/minute")
def get_connectivite_points_geojson(
    request: Request,
    code_postal:    Optional[int] = Query(None),
    arrondissement: Optional[int] = Query(None),
    code_quartier:  Optional[int] = Query(None),
    generation:     Optional[str] = Query(None),
    operateur:      Optional[str] = Query(None),
    _: str = Depends(verify_api_key),
):
    """Points géospatiaux antennes en GeoJSON.
    Filtrable par code_postal, arrondissement, code_quartier, generation, operateur."""
    query = {}

    if code_quartier:
        query["code_quartier"] = code_quartier
    elif arrondissement:
        query["arrondissement"] = arrondissement
    elif code_postal:
        # fallback legacy : code_postal → arrondissement
        query["arrondissement"] = code_postal - 75000

    if generation:
        query["generation"] = generation
    if operateur:
        query["operateur"] = operateur

    docs = list(mongo["silver"]["indicateur_connectivite"].find(query, {"_id": 0}))
    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "code_quartier":  doc.get("code_quartier"),
                "nom_quartier":   doc.get("nom_quartier"),
                "arrondissement": doc.get("arrondissement"),
                "type":           doc.get("type"),
                "code_site":      doc.get("code_site"),
                "generation":     doc.get("generation"),
                "operateur":      doc.get("operateur"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}