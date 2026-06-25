from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/vivabilite", tags=["Vivabilité"])


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS — ARRONDISSEMENT
# --------------------------------------------------------------------------

@router.get("")
@limiter.limit("60/minute")
def get_vivabilite_arrondissement(
    request: Request,
    arrondissement: Optional[int] = Query(None, description="Numéro d'arrondissement (1-20)"),
    _: str = Depends(verify_api_key),
):
    """Score de vivabilité par arrondissement (20 arrondissements).
    Dimensions : propreté, espaces verts, criminalité, bruit, NO2."""
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


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS — QUARTIER
# --------------------------------------------------------------------------

@router.get("/quartier")
@limiter.limit("60/minute")
def get_vivabilite_quartier(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Code quartier (1-80)"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    _: str = Depends(verify_api_key),
):
    """Score de vivabilité par quartier (80 quartiers).
    ⚠️ Basé sur 2 dimensions uniquement : propreté + espaces verts
    (bruit, NO2 et criminalité non disponibles à la granularité quartier).
    Filtrable par arrondissement."""
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
# CLASSEMENT — TOP / BOTTOM N
# --------------------------------------------------------------------------

@router.get("/classement")
@limiter.limit("60/minute")
def get_vivabilite_classement(
    request: Request,
    granularite: str  = Query("arrondissement", description="'arrondissement' ou 'quartier'"),
    top:         int  = Query(5, ge=1, le=20, description="Nombre de résultats à retourner"),
    ordre:       str  = Query("desc", description="'desc' (meilleurs) ou 'asc' (pires)"),
    _: str = Depends(verify_api_key),
):
    """Top ou bottom N des zones par score de vivabilité."""
    table = (
        "gold.score_vivabilite_arrondissement"
        if granularite == "arrondissement"
        else "gold.score_vivabilite_quartier"
    )
    direction = "ASC" if ordre == "asc" else "DESC"
    with get_engine().connect() as conn:
        result = conn.execute(
            text(f"SELECT * FROM {table} ORDER BY score_vivabilite {direction} LIMIT :top"),
            {"top": top},
        )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Aucune donnée trouvée")
    return rows


# --------------------------------------------------------------------------
# POINTS GÉOSPATIAUX GEOJSON (MongoDB)
# --------------------------------------------------------------------------

@router.get("/points/geojson")
@limiter.limit("30/minute")
def get_vivabilite_points_geojson(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Filtre par quartier"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    type_point:     Optional[str] = Query(None, description="'signalement' ou 'espace_vert'"),
    _: str = Depends(verify_api_key),
):
    """Points géospatiaux vivabilité en GeoJSON (signalements propreté, espaces verts)."""
    query = {}
    if code_quartier:
        query["code_quartier"] = code_quartier
    elif arrondissement:
        query["arrondissement"] = arrondissement
    if type_point:
        query["type"] = type_point

    # Si pas de filtre type_point, limiter les signalements mais garder tous les espaces verts
    if type_point:
        docs = list(mongo["silver"]["indicateur_vivabilite_geo"].find(query, {"_id": 0}).limit(1000))
    else:
        query_prop = {**query, "type": "signalement"}
        query_ev   = {**query, "type": "espace_vert"}
        docs = (
            list(mongo["silver"]["indicateur_vivabilite_geo"].find(query_prop, {"_id": 0}).limit(500)) +
            list(mongo["silver"]["indicateur_vivabilite_geo"].find(query_ev,   {"_id": 0}))
        )
    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "arrondissement"  : doc.get("arrondissement"),
                "type"            : doc.get("type"),
                "type_declaration": doc.get("type_declaration"),
                "poids"           : doc.get("poids"),
                "nom"             : doc.get("nom"),
                "type_espace_vert": doc.get("type_espace_vert"),
                "surface_m2"      : doc.get("surface_m2"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}
