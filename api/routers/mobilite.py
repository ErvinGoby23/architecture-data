from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/mobilite", tags=["Mobilité"])

MODE_MAP = {
    "arret_bus":            "Bus",
    "arret_metro":          "Métro",
    "arret_rer":            "RER",
    "arret_tram":           "Tram",
    "arret_train":          "Train",
    "arret_train_regional": "Train Régional",
}


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS
# --------------------------------------------------------------------------

@router.get("")
@limiter.limit("60/minute")
def get_mobilite_arrondissement(
    request: Request,
    arrondissement: Optional[int] = Query(None, description="Numéro d'arrondissement (1-20)"),
    _: str = Depends(verify_api_key),
):
    """Score de mobilité par arrondissement (20 arrondissements)."""
    with get_engine().connect() as conn:
        if arrondissement:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite_arrondissement WHERE arrondissement = :arr"),
                {"arr": arrondissement},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite_arrondissement ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@router.get("/quartier")
@limiter.limit("60/minute")
def get_mobilite_quartier(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Code quartier (1-80)"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    _: str = Depends(verify_api_key),
):
    """Score de mobilité par quartier (80 quartiers). Filtrable par arrondissement."""
    with get_engine().connect() as conn:
        if code_quartier:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite_quartier WHERE code_quartier = :cq"),
                {"cq": code_quartier},
            )
        elif arrondissement:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite_quartier WHERE arrondissement = :arr ORDER BY rang"),
                {"arr": arrondissement},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite_quartier ORDER BY rang")
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
def get_mobilite_points_geojson(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Filtre par quartier"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    type_point:     Optional[str] = Query(None),
    mode_nom:       Optional[str] = Query(None),
    _: str = Depends(verify_api_key),
):
    """Points géospatiaux (arrêts, bornes taxi, stationnement) en GeoJSON.
    Filtrable par quartier, arrondissement, type de point et mode de transport."""
    query = {}

    if code_quartier:
        query["code_quartier"] = code_quartier
    elif arrondissement:
        query["arrondissement"] = arrondissement

    if type_point:
        if type_point.startswith("arret_"):
            query["type"] = "arret"
            mode = MODE_MAP.get(type_point)
            if mode:
                query["mode_nom"] = mode
        else:
            query["type"] = type_point

    if mode_nom:
        query["mode_nom"] = mode_nom

    docs = list(mongo["silver"]["indicateur_mobilite"].find(query, {"_id": 0}))
    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "code_quartier":    doc.get("code_quartier"),
                "nom_quartier":     doc.get("nom_quartier"),
                "arrondissement":   doc.get("arrondissement"),
                "type":             doc.get("type"),
                "mode_nom":         doc.get("mode_nom"),
                "stop_id":          doc.get("stop_id"),
                "route_short_name": doc.get("route_short_name"),
                "borne_id":         doc.get("borne_id"),
                "nom_voie":         doc.get("nom_voie"),
                "places_relevees":  doc.get("places_relevees"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}