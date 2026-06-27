"""
silver_fusion_vivabilite.py — Pipeline Silver · Indicateur 3 : Vivabilité (Fusion)
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER
Le Silver fusionne les données brutes — AUCUN calcul de score ici (appartient au Gold).
"""

import math
import pandas as pd
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE

load_dotenv('../../../.env')

SILVER_BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..',
    'architecture-data', 'silver', 'indicateur3', 'nettoyage-indicateur3'
)

def get_latest_date(silver_dir):
    dates = sorted([
        d for d in os.listdir(silver_dir)
        if os.path.isdir(os.path.join(silver_dir, d))
    ], reverse=True)
    if not dates:
        raise FileNotFoundError(f"Aucun dossier trouvé dans {silver_dir}")
    return dates[0]

date_str = sys.argv[1] if len(sys.argv) > 1 else get_latest_date(SILVER_BASE)
print(f"=== SILVER FUSION (IND3) — date : {date_str} ===")

SILVER_DIR = os.path.join(SILVER_BASE, date_str)
os.makedirs(SILVER_DIR, exist_ok=True)

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver'

# ==========================================================================
# 1. CHARGEMENT + VALIDATION INTÉGRITÉ
# ==========================================================================
print("\n--- CHARGEMENT ---")
df_criminalite = pd.read_parquet(os.path.join(SILVER_DIR, 'criminalite_silver.parquet'))
df_proprete    = pd.read_parquet(os.path.join(SILVER_DIR, 'proprete_silver.parquet'))
df_proprete_qu = pd.read_parquet(os.path.join(SILVER_DIR, 'proprete_quartier_silver.parquet'))
df_espaces     = pd.read_parquet(os.path.join(SILVER_DIR, 'espaces_verts_silver.parquet'))
df_espaces_qu  = pd.read_parquet(os.path.join(SILVER_DIR, 'espaces_verts_quartier_silver.parquet'))
df_no2         = pd.read_parquet(os.path.join(SILVER_DIR, 'NO2_silver.parquet'))

print(f"Criminalite   : {df_criminalite.shape}")
print(f"Proprete arr. : {df_proprete.shape}")
print(f"Proprete qtr. : {df_proprete_qu.shape}")
print(f"Espaces arr.  : {df_espaces.shape}")
print(f"Espaces qtr.  : {df_espaces_qu.shape}")
print(f"NO2           : {df_no2.shape}")

assert df_proprete['arrondissement'].is_unique,    "DOUBLON arrondissement dans proprete_silver"
assert df_proprete_qu['code_quartier'].is_unique,  "DOUBLON code_quartier dans proprete_quartier_silver"
assert df_espaces['arrondissement'].is_unique,     "DOUBLON arrondissement dans espaces_verts_silver"
assert df_espaces_qu['code_quartier'].is_unique,   "DOUBLON code_quartier dans espaces_verts_quartier_silver"
assert df_criminalite['arrondissement'].is_unique, "DOUBLON arrondissement dans criminalite_silver"
assert df_no2['arrondissement'].is_unique,         "DOUBLON arrondissement dans NO2_silver"
print("Integrite des parquets entrants OK")

# ==========================================================================
# 2. PRÉPARATION COLONNES BRUTES
# ==========================================================================
cols_crim = ['arrondissement', 'insee_pop'] + [c for c in df_criminalite.columns if c.startswith('taux_')]
df_crim_s = df_criminalite[[c for c in cols_crim if c in df_criminalite.columns]].copy()

cols_prop = ['arrondissement', 'nb_signalements']
df_prop_s = df_proprete[[c for c in cols_prop if c in df_proprete.columns]].copy()

cols_ev = ['arrondissement', 'nb_espaces_verts']
if 'surface_totale_m2' in df_espaces.columns:
    cols_ev += ['surface_totale_m2', 'surface_moy_m2', 'nb_grands_espaces']
df_ev_s = df_espaces[[c for c in cols_ev if c in df_espaces.columns]].copy()

cols_no2 = ['arrondissement', 'nb_personnes_exposees_no2']
df_no2_s = df_no2[[c for c in cols_no2 if c in df_no2.columns]].copy()
print(f"\nNO2 2019 — apercu : {df_no2_s['nb_personnes_exposees_no2'].describe().to_dict()}")

# ==========================================================================
# 3. FUSION ARRONDISSEMENT — données brutes uniquement
# ==========================================================================
print("\n--- FUSION ARRONDISSEMENT ---")
df_fusion = pd.DataFrame({'arrondissement': range(1, 21)})
df_fusion = df_fusion.merge(df_crim_s,  on='arrondissement', how='left')
df_fusion = df_fusion.merge(df_prop_s,  on='arrondissement', how='left')
df_fusion = df_fusion.merge(df_ev_s,    on='arrondissement', how='left')
df_fusion = df_fusion.merge(df_no2_s,   on='arrondissement', how='left')
df_fusion = df_fusion.fillna(0).sort_values('arrondissement').reset_index(drop=True)
assert len(df_fusion) == 20, f"Fusion arrondissement : {len(df_fusion)} lignes attendues 20"
print(f"Shape fusion arrondissement : {df_fusion.shape}")
print(f"Colonnes : {list(df_fusion.columns)}")

# ==========================================================================
# 4. FUSION QUARTIER — données brutes uniquement
# ==========================================================================
print("\n--- FUSION QUARTIER ---")
ref_qu = df_proprete_qu[['code_quartier', 'nom_quartier', 'arrondissement']].drop_duplicates('code_quartier').copy()

cols_prop_qu = ['code_quartier', 'nb_signalements']
df_prop_qu_s = df_proprete_qu[[c for c in cols_prop_qu if c in df_proprete_qu.columns]].copy()

cols_ev_qu = ['code_quartier', 'nb_espaces_verts']
if 'surface_totale_m2' in df_espaces_qu.columns:
    cols_ev_qu += ['surface_totale_m2', 'surface_moy_m2', 'nb_grands_espaces']
df_ev_qu_s = df_espaces_qu[[c for c in cols_ev_qu if c in df_espaces_qu.columns]].copy()

df_fusion_qu = ref_qu.copy()
df_fusion_qu = df_fusion_qu.merge(df_prop_qu_s, on='code_quartier', how='left')
df_fusion_qu = df_fusion_qu.merge(df_ev_qu_s,   on='code_quartier', how='left')
df_fusion_qu = df_fusion_qu.fillna(0).sort_values('code_quartier').reset_index(drop=True)
print(f"Shape fusion quartier : {df_fusion_qu.shape}")
print(f"Quartiers uniques     : {df_fusion_qu['code_quartier'].nunique()}")
assert len(df_fusion_qu) == df_fusion_qu['code_quartier'].nunique(), \
    f"Doublons détectés après fusion quartier : {len(df_fusion_qu)} lignes / {df_fusion_qu['code_quartier'].nunique()} uniques"

# ==========================================================================
# 5. EXPORT PARQUET versionné
# ==========================================================================
parquet_arr = os.path.join(SILVER_DIR, 'indicateur_vivabilite_silver.parquet')
parquet_qu  = os.path.join(SILVER_DIR, 'indicateur_vivabilite_quartier_silver.parquet')
df_fusion.to_parquet(parquet_arr, index=False)
df_fusion_qu.to_parquet(parquet_qu, index=False)
print(f"\nParquet arrondissement : {parquet_arr}  ({len(df_fusion)} lignes)")
print(f"Parquet quartier       : {parquet_qu}  ({len(df_fusion_qu)} lignes)")

# ==========================================================================
# 6. POSTGRESQL — 2 tables silver (données brutes)
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS silver;'))
        conn.execute(text('DROP TABLE IF EXISTS silver.indicateur_vivabilite CASCADE;'))
        conn.execute(text('DROP TABLE IF EXISTS silver.indicateur_vivabilite_quartier CASCADE;'))
        conn.commit()

    df_fusion.to_sql('indicateur_vivabilite', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_vivabilite ADD PRIMARY KEY (arrondissement)"))
        conn.commit()
    print(f"PostgreSQL : silver.indicateur_vivabilite ({len(df_fusion)} lignes)")

    df_fusion_qu.to_sql('indicateur_vivabilite_quartier', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_vivabilite_quartier ADD PRIMARY KEY (code_quartier)"))
        conn.commit()
    print(f"PostgreSQL : silver.indicateur_vivabilite_quartier ({len(df_fusion_qu)} lignes)")
except Exception as e:
    print(f"PostgreSQL indisponible : {e}")

# ==========================================================================
# 7. MONGODB — espaces verts + signalements propreté
# ==========================================================================
try:
    import geopandas as gpd
    from shapely.geometry import Point

    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_vivabilite'].drop()

    print("\n--- TRAITEMENT SPATIAL ---")
    url_arrondissements = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/arrondissements/exports/geojson"
    gdf_paris = gpd.read_file(url_arrondissements)
    if 'c_ar' in gdf_paris.columns:
        gdf_paris['true_arr'] = gdf_paris['c_ar'].astype(int)
    else:
        gdf_paris['true_arr'] = gdf_paris['c_arinsee'].astype(int) % 100

    def purge_nan(df_in):
        df_out = df_in.copy()
        for col in df_out.select_dtypes(include="float").columns:
            mask = df_out[col].notna() & ~df_out[col].isin([float('inf'), float('-inf')])
            df_out[col] = df_out[col].where(mask, other=None).astype(object)
        return df_out

    def sanitize_docs(docs):
        """Convertit pd.NA / NaN / inf restants en None pour JSON/MongoDB."""
        for doc in docs:
            for k, v in doc.items():
                if v is pd.NA:
                    doc[k] = None
                elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    doc[k] = None
        return docs

    def to_geo_docs(df_in, type_label, cols_props):
        df_g = df_in.dropna(subset=['latitude', 'longitude']).copy()
        geometry = [Point(xy) for xy in zip(df_g['longitude'], df_g['latitude'])]
        gdf_points = gpd.GeoDataFrame(df_g, geometry=geometry, crs="EPSG:4326")
        gdf_joined = gpd.sjoin(gdf_points, gdf_paris[['true_arr', 'geometry']], how='left', predicate='within')
        gdf_joined['arrondissement'] = gdf_joined['true_arr']
        df_clean = pd.DataFrame(gdf_joined.drop(columns=['geometry', 'index_right', 'true_arr']))
        df_clean = purge_nan(df_clean)
        df_clean['geo'] = [
            {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
            for lon, lat in zip(df_clean['longitude'], df_clean['latitude'])
        ]
        df_clean['type'] = type_label
        df_clean['code_quartier'] = pd.array(df_clean['code_quartier'], dtype='Int64')
        df_clean = df_clean.dropna(subset=['arrondissement'])
        df_clean['arrondissement'] = df_clean['arrondissement'].astype(int)
        keep = ['type', 'arrondissement', 'code_quartier', 'nom_quartier', 'geo'] + cols_props
        return sanitize_docs(df_clean[[c for c in keep if c in df_clean.columns]].to_dict(orient='records'))

    def to_geo_docs_proprete(df_in, cols_props):
        df_g = df_in.dropna(subset=['latitude', 'longitude']).copy()
        geometry = [Point(xy) for xy in zip(df_g['longitude'], df_g['latitude'])]
        gdf_points = gpd.GeoDataFrame(df_g, geometry=geometry, crs="EPSG:4326")
        gdf_joined = gpd.sjoin(gdf_points, gdf_paris[['true_arr', 'geometry']], how='left', predicate='within')
        gdf_joined['arrondissement'] = gdf_joined['true_arr']
        df_clean = pd.DataFrame(gdf_joined.drop(columns=['geometry', 'index_right', 'true_arr']))
        df_clean = purge_nan(df_clean)
        df_clean['geo'] = [
            {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
            for lon, lat in zip(df_clean['longitude'], df_clean['latitude'])
        ]
        df_clean['type'] = df_clean['type_declaration'].fillna('signalement')
        df_clean['code_quartier'] = pd.array(df_clean['code_quartier'], dtype='Int64')
        df_clean = df_clean.dropna(subset=['arrondissement'])
        df_clean['arrondissement'] = df_clean['arrondissement'].astype(int)
        keep = ['type', 'arrondissement', 'code_quartier', 'nom_quartier', 'geo'] + cols_props
        return sanitize_docs(df_clean[[c for c in keep if c in df_clean.columns]].to_dict(orient='records'))

    all_docs = []

    ev_path = os.path.join(SILVER_DIR, 'espaces_verts_long_silver.parquet')
    if os.path.exists(ev_path):
        df_ev_long = pd.read_parquet(ev_path)
        docs_ev = to_geo_docs(df_ev_long, 'espace_vert', ['nom', 'type_espace_vert', 'surface_m2'])
        all_docs.extend(docs_ev)
        print(f"  Espaces verts : {len(docs_ev):,} docs")

    prop_path = os.path.join(SILVER_DIR, 'proprete_long_silver.parquet')
    if os.path.exists(prop_path):
        df_prop_long = pd.read_parquet(prop_path)
        if len(df_prop_long) > 20000:
            df_prop_long = df_prop_long.sample(n=20000, random_state=42)
        types_distincts = sorted(df_prop_long['type_declaration'].dropna().unique())
        print(f"  Types signalements dans Mongo : {types_distincts}")
        docs_prop = to_geo_docs_proprete(df_prop_long, ['id_declaration', 'type_declaration', 'mois'])
        all_docs.extend(docs_prop)
        print(f"  Signalements (echantillonnes) : {len(docs_prop):,} docs")

    if all_docs:
        mongo['indicateur_vivabilite'].insert_many(all_docs, ordered=False)

    mongo['indicateur_vivabilite'].create_index([("geo", GEOSPHERE)])
    mongo['indicateur_vivabilite'].create_index([("code_quartier", 1)])
    mongo['indicateur_vivabilite'].create_index([("arrondissement", 1)])
    mongo['indicateur_vivabilite'].create_index([("type", 1)])
    print(f"MongoDB : Importation reussie et index crees.")

except Exception as e:
    print(f"MongoDB indisponible ou erreur traitement : {e}")

print('\n=== SILVER VIVABILITE OK ===')
print(f"Arrondissement — {len(df_fusion)} lignes, {len(df_fusion.columns)} colonnes")
print(f"Quartier       — {len(df_fusion_qu)} lignes, {len(df_fusion_qu.columns)} colonnes")