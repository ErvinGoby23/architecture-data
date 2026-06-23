# routers/services.py
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/services", tags=["Services du Quotidien"])


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS
# --------------------------------------------------------------------------

@router.get("")
@limiter.limit("60/minute")
def get_services_arrondissement(
    request: Request,
    code_postal:    Optional[int] = Query(None, description="Filtrer par code postal (ex: 75011)"),
    arrondissement: Optional[int] = Query(None, description="Filtrer par arrondissement (1-20)"),
    _: str = Depends(verify_api_key),
):
    """Score des services du quotidien par arrondissement (20 arrondissements)."""
    # On accepte soit code_postal (75011) soit arrondissement (11)
    cp = code_postal
    if cp is None and arrondissement is not None:
        cp = 75000 + arrondissement

    with get_engine().connect() as conn:
        if cp:
            result = conn.execute(
                text("SELECT * FROM gold.score_services WHERE code_postal = :cp"),
                {"cp": cp},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_services ORDER BY rang")
            )
        rows = [dict(r._mapping) for r in result]

    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


@router.get("/quartier")
@limiter.limit("60/minute")
def get_services_quartier(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Code quartier (1-80)"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    _: str = Depends(verify_api_key),
):
    """Score des services du quotidien par quartier (80 quartiers). Filtrable par arrondissement."""
    with get_engine().connect() as conn:
        if code_quartier:
            result = conn.execute(
                text("SELECT * FROM gold.score_services_quartier WHERE code_quartier = :cq"),
                {"cq": code_quartier},
            )
        elif arrondissement:
            result = conn.execute(
                text("SELECT * FROM gold.score_services_quartier WHERE arrondissement = :arr ORDER BY rang"),
                {"arr": arrondissement},
            )
        else:
            result = conn.execute(
                text("SELECT * FROM gold.score_services_quartier ORDER BY rang")
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
def get_services_points_geojson(
    request: Request,
    code_quartier:  Optional[int] = Query(None, description="Filtre par quartier"),
    arrondissement: Optional[int] = Query(None, description="Filtre par arrondissement"),
    code_postal:    Optional[int] = Query(None, description="Filtre par code postal"),
    type_service:   Optional[str] = Query(None, description="Filtrer par type ('ecole' ou 'commissariat')"),
    _: str = Depends(verify_api_key),
):
    """Points géographiques des écoles et commissariats au format GeoJSON (MongoDB).
    Filtrable par quartier, arrondissement (ou code postal) et type de service."""
    query = {}

    if code_quartier:
        query["code_quartier"] = code_quartier
    elif arrondissement:
        # Les documents services portent code_postal (pas arrondissement) -> conversion
        query["code_postal"] = 75000 + arrondissement
    elif code_postal:
        query["code_postal"] = code_postal

    if type_service:
        query["type"] = type_service

    # On interroge la collection créée lors de la fusion Silver
    docs = list(mongo["silver"]["indicateur_services_geo"].find(query, {"_id": 0}))

    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "code_postal":       doc.get("code_postal"),
                "code_quartier":     doc.get("code_quartier"),
                "nom_quartier":      doc.get("nom_quartier"),
                "type":              doc.get("type"),
                "nom":               doc.get("etablissement_nom") or doc.get("commissariat_nom") or "Non renseigné",
                "type_commissariat": doc.get("type_commissariat"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}