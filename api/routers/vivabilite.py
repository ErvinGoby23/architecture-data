from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/vivabilite", tags=["Vivabilité"])


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS
# --------------------------------------------------------------------------

@router.get("")
@limiter.limit("60/minute")
def get_vivabilite_arrondissement(
    request: Request,
    arrondissement: Optional[int] = Query(None, description="Numéro d'arrondissement (1-20)"),
    _: str = Depends(verify_api_key),
):
    """Score de vivabilité par arrondissement (20 arrondissements)."""
    with get_engine().connect() as conn:
        if arrondissement:
            result = conn.execute(
                text("SELECT * FROM gold.score_vivabilite_arrondissement WHERE arrondissement = :arr"),
                {"arr": arrondissement},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_vivabilite_arrondissement ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@router.get("/quartier")
@limiter.limit("60/minute")
def get_vivabilite_quartier(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Code quartier (1-80)"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    _: str = Depends(verify_api_key),
):
    """Score de vivabilité par quartier (80 quartiers). Filtrable par arrondissement."""
    with get_engine().connect() as conn:
        if code_quartier:
            result = conn.execute(
                text("SELECT * FROM gold.score_vivabilite_quartier WHERE code_quartier = :cq"),
                {"cq": code_quartier},
            )
        elif arrondissement:
            result = conn.execute(
                text("SELECT * FROM gold.score_vivabilite_quartier WHERE arrondissement = :arr ORDER BY rang"),
                {"arr": arrondissement},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_vivabilite_quartier ORDER BY rang")
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
def get_vivabilite_points_geojson(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Filtre par quartier"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    type_point:     Optional[str] = Query(None, description="espace_vert | signalement"),
    _: str = Depends(verify_api_key),
):
    """Points géospatiaux (espaces verts, signalements propreté) en GeoJSON."""
    query = {}

    if code_quartier:
        query["code_quartier"] = code_quartier
    elif arrondissement:
        query["arrondissement"] = arrondissement

    if type_point:
        query["type"] = type_point

    docs = list(mongo["silver"]["indicateur_vivabilite"].find(query, {"_id": 0}))
    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "code_quartier":    doc.get("code_quartier"),
                "nom_quartier":     doc.get("nom_quartier"),
                "arrondissement":   doc.get("arrondissement"),
                "type":             doc.get("type"),
                "nom":              doc.get("nom"),
                "type_espace_vert": doc.get("type_espace_vert"),
                "surface_m2":       doc.get("surface_m2"),
                "id_declaration":   doc.get("id_declaration"),
                "type_declaration": doc.get("type_declaration"),
                "poids":            doc.get("poids"),
                "mois":             doc.get("mois"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}