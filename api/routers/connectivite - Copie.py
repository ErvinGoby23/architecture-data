from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/connectivite", tags=["Connectivité"])

@router.get("")
@limiter.limit("500/minute")
def get_connectivite(
    request: Request,
    code_postal: Optional[int] = Query(None),
    annee: Optional[int] = Query(None),
    _: str = Depends(verify_api_key),
):
    with get_engine().connect() as conn:
        if code_postal and annee:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite WHERE code_postal = :cp AND annee = :annee"),
                {"cp": code_postal, "annee": annee},
            )
        elif code_postal:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite WHERE code_postal = :cp ORDER BY annee"),
                {"cp": code_postal},
            )
        elif annee:
            result = conn.execute(
                text("SELECT * FROM gold.score_connectivite WHERE annee = :annee ORDER BY rang"),
                {"annee": annee},
            )
        else:
            result = conn.execute(
                text("""
                    SELECT * FROM gold.score_connectivite
                    WHERE annee = (SELECT MAX(annee) FROM gold.score_connectivite)
                    ORDER BY rang
                """)
            )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@router.get("/points/geojson")
@limiter.limit("500/minute")
def get_connectivite_points_geojson(
    request: Request,
    code_postal: Optional[int] = Query(None),
    generation:  Optional[str] = Query(None),
    operateur:   Optional[str] = Query(None),
    _: str = Depends(verify_api_key),
):
    query = {}
    if code_postal:
        query["code_postal"] = code_postal
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
                "code_postal": doc.get("code_postal"),
                "type":        doc.get("type"),
                "code_site":   doc.get("code_site"),
                "generation":  doc.get("generation"),
                "operateur":   doc.get("operateur"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}