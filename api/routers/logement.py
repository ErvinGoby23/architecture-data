from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from typing import Optional
from dependencies import verify_api_key, get_engine, mongo, limiter

router = APIRouter(prefix="/logement", tags=["Logement"])


# --------------------------------------------------------------------------
# SCORES AGRÉGÉS — ARRONDISSEMENT
# --------------------------------------------------------------------------

@router.get("")
@limiter.limit("60/minute")
def get_logement(
    request: Request,
    code_postal: Optional[int] = Query(None),
    arrondissement: Optional[int] = Query(None),
    annee: Optional[int] = Query(None),
    _: str = Depends(verify_api_key),
):
    """Score d'accessibilité du logement par arrondissement.
    Filtrable par arrondissement (ou code_postal) et par année (timeline)."""
    # code_postal -> arrondissement (compat)
    arr = arrondissement if arrondissement else (code_postal - 75000 if code_postal else None)

    clauses, params = [], {}
    if arr:
        clauses.append("arrondissement = :arr")
        params["arr"] = arr
    if annee:
        clauses.append("annee = :annee")
        params["annee"] = annee
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order = " ORDER BY annee, rang"

    with get_engine().connect() as conn:
        result = conn.execute(
            text(f"SELECT * FROM gold.score_accessibilite_logement{where}{order}"),
            params,
        )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Aucune donnée logement trouvée")
    return rows


@router.get("/quartier")
@limiter.limit("60/minute")
def get_logement_quartier(
    request: Request,
    code_quartier: Optional[int] = Query(None),
    arrondissement: Optional[int] = Query(None),
    annee: Optional[int] = Query(None),
    _: str = Depends(verify_api_key),
):
    """Score d'accessibilité du logement par quartier (80 quartiers).
    Filtrable par code_quartier, arrondissement et année."""
    clauses, params = [], {}
    if code_quartier:
        clauses.append("code_quartier = :cq")
        params["cq"] = code_quartier
    elif arrondissement:
        clauses.append("arrondissement = :arr")
        params["arr"] = arrondissement
    if annee:
        clauses.append("annee = :annee")
        params["annee"] = annee
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order = " ORDER BY annee, rang"

    with get_engine().connect() as conn:
        result = conn.execute(
            text(f"SELECT * FROM gold.score_accessibilite_logement_quartier{where}{order}"),
            params,
        )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Quartier non trouvé")
    return rows


# --------------------------------------------------------------------------
# TIMELINE — évolution d'un arrondissement dans le temps
# --------------------------------------------------------------------------

@router.get("/timeline")
@limiter.limit("60/minute")
def get_logement_timeline(
    request: Request,
    arrondissement: int = Query(..., description="Arrondissement (1-20)"),
    _: str = Depends(verify_api_key),
):
    """Série temporelle complète d'un arrondissement (pour la timeline du dashboard)."""
    with get_engine().connect() as conn:
        result = conn.execute(
            text(
                "SELECT annee, prix_m2_median, nb_logements, taux_effort_achat, "
                "score_accessibilite_100, rang "
                "FROM gold.score_accessibilite_logement "
                "WHERE arrondissement = :arr ORDER BY annee"
            ),
            {"arr": arrondissement},
        )
        rows = [dict(r._mapping) for r in result]
    if not rows:
        raise HTTPException(status_code=404, detail="Arrondissement non trouvé")
    return rows


# --------------------------------------------------------------------------
# POINTS GÉOSPATIAUX GEOJSON
# --------------------------------------------------------------------------

@router.get("/points/geojson")
@limiter.limit("30/minute")
def get_logement_points_geojson(
    request: Request,
    code_postal: Optional[int] = Query(None),
    arrondissement: Optional[int] = Query(None),
    code_quartier: Optional[int] = Query(None),
    annee: Optional[int] = Query(None),
    type: Optional[str] = Query(None, description="transaction | logement_social"),
    _: str = Depends(verify_api_key),
):
    """Points géospatiaux logement en GeoJSON (transactions DVF + programmes sociaux).
    Filtrable par code_postal, arrondissement, code_quartier, année, type."""
    query = {}

    if code_quartier:
        query["code_quartier"] = code_quartier
    elif arrondissement:
        query["arrondissement"] = arrondissement
    elif code_postal:
        query["arrondissement"] = code_postal - 75000

    if annee:
        query["annee"] = annee
    if type:
        query["type"] = type

    docs = list(mongo["silver"]["indicateur_logement"].find(query, {"_id": 0}))
    features = [
        {
            "type": "Feature",
            "geometry": doc["geo"],
            "properties": {
                "type": doc.get("type"),
                "code_quartier": doc.get("code_quartier"),
                "nom_quartier": doc.get("nom_quartier"),
                "arrondissement": doc.get("arrondissement"),
                "annee": doc.get("annee"),
                "prix_m2": doc.get("prix_m2"),
                "surface": doc.get("surface"),
                "nb_logements": doc.get("nb_logements"),
                "nature_programme": doc.get("nature_programme"),
                "bailleur": doc.get("bailleur"),
            },
        }
        for doc in docs
        if doc.get("geo")
    ]
    return {"type": "FeatureCollection", "features": features}
