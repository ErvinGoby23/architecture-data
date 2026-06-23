# routers/services.py
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/services", tags=["Services du Quotidien"])

@router.get("")
@limiter.limit("60/minute")
def get_services(
    request: Request,
    code_postal: Optional[int] = Query(None, description="Filtrer par code postal (ex: 75011)"),
    _: str = Depends(verify_api_key),
):
    """
    Récupère les scores et statistiques agrégées des services du quotidien (PostgreSQL).
    """
    with get_engine().connect() as conn:
        if code_postal:
            result = conn.execute(
                text("SELECT * FROM gold.score_services WHERE code_postal = :cp"),
                {"cp": code_postal},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_services ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]
        
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    
    return rows


@router.get("/points/geojson")
@limiter.limit("30/minute")
def get_services_points_geojson(
    request: Request,
    code_postal: Optional[int] = Query(None, description="Filtrer par code postal"),
    type_service: Optional[str] = Query(None, description="Filtrer par type ('ecole' ou 'commissariat')"),
    _: str = Depends(verify_api_key),
):
    """
    Récupère les points géographiques des écoles et commissariats au format GeoJSON (MongoDB).
    """
    query = {}
    if code_postal:
        query["code_postal"] = code_postal
    if type_service:
        query["type"] = type_service

    # On interroge la collection créée lors de la fusion Silver
    docs = list(mongo["silver"]["indicateur_services_geo"].find(query, {"_id": 0}))
    
    features = []
    for doc in docs:
        if doc.get("geo"):
            # On unifie le nom de l'établissement/commissariat sous une propriété "nom" générique
            nom = doc.get("etablissement_nom") or doc.get("commissariat_nom") or "Non renseigné"
            
            features.append({
                "type": "Feature",
                "geometry": doc["geo"],
                "properties": {
                    "code_postal": doc.get("code_postal"),
                    "type": doc.get("type"),
                    "nom": nom
                },
            })
            
    return {"type": "FeatureCollection", "features": features}