from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, engine, mongo, limiter

router = APIRouter(prefix="/mobilite", tags=["Mobilité"])

MODE_MAP = {
    "arret_bus":            "Bus",
    "arret_metro":          "Métro",
    "arret_rer":            "RER",
    "arret_tram":           "Tram",
    "arret_train":          "Train",
    "arret_train_regional": "Train Régional",
}

@router.get("")
@limiter.limit("2/minute")
def get_mobilite(
    request: Request,
    code_postal: Optional[int] = Query(None),
    _: str = Depends(verify_api_key),
):
    with engine.connect() as conn:
        if code_postal:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite WHERE code_postal = :cp"),
                {"cp": code_postal},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_mobilite ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@router.get("/points/geojson")
@limiter.limit("1/minute")
def get_mobilite_points_geojson(
    request: Request,
    code_postal: Optional[int] = Query(None),
    type_point:  Optional[str] = Query(None),
    mode_nom:    Optional[str] = Query(None),
    _: str = Depends(verify_api_key),
):
    query = {}
    if code_postal:
        query["code_postal"] = code_postal
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
                "code_postal":      doc.get("code_postal"),
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