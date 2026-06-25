"""
FUSION SILVER — Indicateurs de logement
========================================
Fusionne les sources Silver de l'indicateur logement.

TABLE 1 — arrondissement × année (DVF + LS + FILOSOFI broadcast)
TABLE 2 — quartier × année       (DVF + LS uniquement, FILOSOFI non disponible à ce niveau)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE

# modules Silver (réutilisés pour reconstruire les points géolocalisés)
import silver_dvf as SDVF
import silver_logements_sociaux as SLS

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".." / ".." / ".." / ".env")

PG_URL = os.getenv("PG_URL")
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB = "silver"
MONGO_COLLECTION = "indicateur_logement"

SILVER_BASE = BASE_DIR / "nettoyage-indicateur5"
GOLD_OUTPUT_DIR = BASE_DIR / "indicateur_logement"
GOLD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=== FUSION SILVER : INDICATEURS DE LOGEMENT ===")

def get_latest_date(silver_dir: Path) -> str:
    dates = sorted(
        [d.name for d in silver_dir.iterdir() if d.is_dir()],
        reverse=True,
    )
    if not dates:
        raise FileNotFoundError(f"Aucun dossier trouvé dans {silver_dir}")
    return dates[0]

if len(sys.argv) > 1:
    date_str = sys.argv[1]
else:
    date_str = get_latest_date(SILVER_BASE)

SILVER_DIR = SILVER_BASE / date_str
print(f"Date silver utilisée : {date_str}")
print(f"Dossier silver       : {SILVER_DIR}")

# ==========================================================================
# 1. LECTURE DES SOURCES SILVER
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")

df_dvf    = pd.read_parquet(SILVER_DIR / "dvf_silver.parquet")
df_dvf_qu = pd.read_parquet(SILVER_DIR / "dvf_silver_quartier.parquet")
df_ls     = pd.read_parquet(SILVER_DIR / "logements_sociaux_silver.parquet")
df_ls_qu  = pd.read_parquet(SILVER_DIR / "logements_sociaux_silver_quartier.parquet")
df_filo   = pd.read_parquet(SILVER_DIR / "filosofi_silver.parquet")

print(f"DVF arr       : {df_dvf.shape}")
print(f"DVF quartier  : {df_dvf_qu.shape}")
print(f"LS arr        : {df_ls.shape}")
print(f"LS quartier   : {df_ls_qu.shape}")
print(f"FILOSOFI      : {df_filo.shape}")

# ==========================================================================
# 2. FUSION ARRONDISSEMENT (DVF + LS + FILOSOFI broadcast)
# ==========================================================================
print("\n--- FUSION ARRONDISSEMENT ---")

for d in (df_dvf, df_ls, df_filo):
    if "cle" in d.columns:
        d.drop(columns=["cle"], inplace=True)

df_filo = df_filo.rename(columns={"millesime": "filosofi_millesime"})

df_arr = df_dvf.merge(df_ls, on=["arrondissement", "annee"], how="outer")
df_arr = df_arr[df_arr["annee"] >= 2021]
df_arr = df_arr.merge(df_filo, on="arrondissement", how="left")

SURFACE_REF = 60
df_arr["prix_bien_60m2"] = (df_arr["prix_m2_median"] * SURFACE_REF).round(0)
df_arr["taux_effort_achat"] = (df_arr["prix_bien_60m2"] / df_arr["revenu_median"]).round(1)

df_arr = df_arr[df_arr["arrondissement"].between(1, 20)]
df_arr = df_arr.dropna(subset=["arrondissement", "annee"])
df_arr["arrondissement"] = df_arr["arrondissement"].astype(int)
df_arr["annee"] = df_arr["annee"].astype(int)

count_cols = ["nb_ventes", "nb_logements", "nb_plai", "nb_plus", "nb_plus_cd", "nb_pls", "nb_programmes"]
for c in count_cols:
    if c in df_arr.columns:
        df_arr[c] = df_arr[c].fillna(0).astype(int)

df_arr["cle"] = df_arr["arrondissement"].map("{:02d}".format) + "_" + df_arr["annee"].astype(str)
front = ["cle", "arrondissement", "annee"]
df_arr = df_arr[front + [c for c in df_arr.columns if c not in front]].sort_values(
    ["arrondissement", "annee"]).reset_index(drop=True)

print(f"Shape arrondissement : {df_arr.shape}")

# ==========================================================================
# 3. FUSION QUARTIER (DVF + LS uniquement)
# ==========================================================================
print("\n--- FUSION QUARTIER ---")

for d in (df_dvf_qu, df_ls_qu):
    if "cle" in d.columns:
        d.drop(columns=["cle"], inplace=True)

df_qu = df_dvf_qu.merge(
    df_ls_qu,
    on=["code_quartier", "annee"],
    how="outer",
    suffixes=("", "_ls"),
)
df_qu = df_qu[df_qu["annee"] >= 2021]

if "arrondissement_ls" in df_qu.columns:
    df_qu["arrondissement"] = df_qu["arrondissement"].fillna(df_qu["arrondissement_ls"])
    df_qu.drop(columns=["arrondissement_ls"], inplace=True)
if "nom_quartier_ls" in df_qu.columns:
    df_qu["nom_quartier"] = df_qu["nom_quartier"].fillna(df_qu["nom_quartier_ls"])
    df_qu.drop(columns=["nom_quartier_ls"], inplace=True)

df_qu = df_qu.dropna(subset=["code_quartier", "annee"])
df_qu["code_quartier"] = df_qu["code_quartier"].astype(int)
df_qu["annee"] = df_qu["annee"].astype(int)

for c in count_cols:
    if c in df_qu.columns:
        df_qu[c] = df_qu[c].fillna(0).astype(int)

df_qu["cle"] = df_qu["code_quartier"].astype(str) + "_" + df_qu["annee"].astype(str)
front_qu = ["cle", "code_quartier", "nom_quartier", "arrondissement", "annee"]
df_qu = df_qu[front_qu + [c for c in df_qu.columns if c not in front_qu]].sort_values(
    ["code_quartier", "annee"]).reset_index(drop=True)

print(f"Shape quartier : {df_qu.shape}")
print(f"Quartiers      : {df_qu['code_quartier'].nunique()}")

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
parquet_arr = SILVER_DIR / "indicateur_logement_silver.parquet"
parquet_qu  = SILVER_DIR / "indicateur_logement_quartier_silver.parquet"
df_arr.to_parquet(parquet_arr, index=False)
df_qu.to_parquet(parquet_qu, index=False)
print(f"\n✓ Parquet arrondissement : {parquet_arr}")
print(f"✓ Parquet quartier       : {parquet_qu}")

# ==========================================================================
# 5. POSTGRESQL
# ==========================================================================
if PG_URL:
    try:
        engine = create_engine(PG_URL)
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
            conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_logement CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_logement_quartier CASCADE;"))
            conn.commit()

        df_arr.to_sql("indicateur_logement", engine, if_exists="replace", index=False, schema="silver")
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE silver.indicateur_logement ADD PRIMARY KEY (cle)"))
            conn.commit()
        print(f"✓ PostgreSQL : silver.indicateur_logement ({len(df_arr)} lignes)")

        df_qu.to_sql("indicateur_logement_quartier", engine, if_exists="replace", index=False, schema="silver")
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE silver.indicateur_logement_quartier ADD PRIMARY KEY (cle)"))
            conn.commit()
        print(f"✓ PostgreSQL : silver.indicateur_logement_quartier ({len(df_qu)} lignes)")

    except Exception as e:
        print(f"❌ PostgreSQL indisponible — export ignoré : {e}")
else:
    print("ℹ PG_URL absent du .env — export PostgreSQL ignoré.")

# ==========================================================================
# 6. POINTS GÉOSPATIAUX -> MONGODB (transactions DVF + programmes sociaux)
# ==========================================================================
print("\n--- INSERTION DES POINTS GÉOSPATIAUX DANS MONGODB ---")


def _build_points_dvf():
    """Transactions DVF unitaires (1 point = 1 vente, avec prix) -> documents GeoJSON."""
    import geopandas as gpd

    df = SDVF.load_bronze(SDVF.BRONZE)
    df = SDVF.prefiltre_paris(df)
    df = SDVF.clean(df)
    appt = SDVF.filtre_metier(df)  # 1 ligne = 1 mutation, prix_m2 calculé

    gdf_qu = SDVF._charger_quartiers_gdf()
    pts = appt.dropna(subset=["longitude", "latitude"]).copy()
    g = gpd.GeoDataFrame(
        pts, geometry=gpd.points_from_xy(pts["longitude"], pts["latitude"]),
        crs="EPSG:4326")
    j = gpd.sjoin(g, gdf_qu, how="left", predicate="within")
    j = j.rename(columns={"C_QU": "code_quartier", "L_QU": "nom_quartier"})
    j = j.drop(columns=[c for c in j.columns if c.startswith("index_right")], errors="ignore")
    j["code_quartier"] = pd.to_numeric(j["code_quartier"], errors="coerce")

    docs = []
    for _, r in j.iterrows():
        docs.append({
            "type": "transaction",
            "geo": {"type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])]},
            "code_postal": int(r["arrondissement"]) + 75000,
            "arrondissement": int(r["arrondissement"]),
            "code_quartier": int(r["code_quartier"]) if pd.notna(r["code_quartier"]) else None,
            "nom_quartier": r.get("nom_quartier"),
            "annee": int(r["annee"]),
            "prix_m2": round(float(r["prix_m2"]), 0),
            "valeur_fonciere": float(r["valeur_fonciere"]),
            "surface": float(r["surface_reelle_bati"]),
        })
    return docs


def _build_points_ls():
    """Programmes de logements sociaux (1 point = 1 programme) -> documents GeoJSON."""
    import geopandas as gpd

    df = SLS.load_bronze(SLS.resolve_bronze())
    df = SLS.clean(df)

    gdf_qu = SLS._charger_quartiers_gdf()
    pts = df.dropna(subset=["x_l93", "y_l93"]).copy()
    g = gpd.GeoDataFrame(
        pts, geometry=gpd.points_from_xy(pts["x_l93"], pts["y_l93"]),
        crs="EPSG:2154").to_crs("EPSG:4326")
    j = gpd.sjoin(g, gdf_qu, how="left", predicate="within")
    j = j.rename(columns={"C_QU": "code_quartier", "L_QU": "nom_quartier"})
    j = j.drop(columns=[c for c in j.columns if c.startswith("index_right")], errors="ignore")
    j["code_quartier"] = pd.to_numeric(j["code_quartier"], errors="coerce")

    docs = []
    for idx, r in j.iterrows():
        lon, lat = j.geometry.loc[idx].x, j.geometry.loc[idx].y
        docs.append({
            "type": "logement_social",
            "geo": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "code_postal": int(r["arrondissement"]) + 75000,
            "arrondissement": int(r["arrondissement"]),
            "code_quartier": int(r["code_quartier"]) if pd.notna(r["code_quartier"]) else None,
            "nom_quartier": r.get("nom_quartier"),
            "annee": int(r["annee"]),
            "nb_logements": int(r["nb_logements"]) if pd.notna(r.get("nb_logements")) else 0,
            "nature_programme": r.get("nature_programme"),
            "bailleur": r.get("bailleur"),
        })
    return docs


if MONGO_URL:
    try:
        dvf_docs = _build_points_dvf()
        print(f"   ↳ DVF : {len(dvf_docs)} transactions géolocalisées")
        ls_docs = _build_points_ls()
        print(f"   ↳ LS  : {len(ls_docs)} programmes géolocalisés")

        client = MongoClient(MONGO_URL)
        mongo = client[MONGO_DB]
        mongo[MONGO_COLLECTION].drop()

        if dvf_docs:
            mongo[MONGO_COLLECTION].insert_many(dvf_docs, ordered=False)
        if ls_docs:
            mongo[MONGO_COLLECTION].insert_many(ls_docs, ordered=False)

        mongo[MONGO_COLLECTION].create_index([("geo", GEOSPHERE)])
        mongo[MONGO_COLLECTION].create_index([("code_postal", 1)])
        mongo[MONGO_COLLECTION].create_index([("code_quartier", 1)])
        mongo[MONGO_COLLECTION].create_index([("annee", 1)])
        mongo[MONGO_COLLECTION].create_index([("type", 1)])

        total = mongo[MONGO_COLLECTION].count_documents({})
        print(f"✓ MongoDB : {MONGO_DB}.{MONGO_COLLECTION} ({total} documents) + index 2dsphere")
    except Exception as e:
        print(f"❌ MongoDB indisponible — points ignorés : {e}")
else:
    print("ℹ MONGO_URL absent du .env — export MongoDB ignoré.")

print("\n=== FUSION SILVER LOGEMENT TERMINÉE ===")