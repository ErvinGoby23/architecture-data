"""
silver_fusion_services.py — Fusion Indicateur 4 (Services du quotidien)
Urban Data Explorer · Silver layer
"""

import pandas as pd
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.normpath(os.path.join(BASE_DIR, '..', '..', '..', '.env')))

SILVER_BASE = 'nettoyage-indicateur4'

def get_latest_date(silver_dir):
    dates = sorted([
        d for d in os.listdir(silver_dir)
        if os.path.isdir(os.path.join(silver_dir, d))
    ], reverse=True)
    if not dates:
        raise FileNotFoundError(f"Aucun dossier trouvé dans {silver_dir}")
    return dates[0]

if len(sys.argv) > 1:
    date_str = sys.argv[1]
else:
    date_str = get_latest_date(SILVER_BASE)

print(f"=== SILVER FUSION (IND4) — date : {date_str} ===")

SILVER_OUTPUT_DIR = os.path.join(BASE_DIR, SILVER_BASE, date_str)
os.makedirs(SILVER_OUTPUT_DIR, exist_ok=True)

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver'

# ==========================================================================
# 1. LECTURE PARQUET
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")

PATH_ECOLES = os.path.join(BASE_DIR, SILVER_BASE, date_str, 'ecoles_elementaires_paris_silver.parquet')
PATH_COMMIS = os.path.join(BASE_DIR, SILVER_BASE, date_str, 'commissariats_paris_silver.parquet')
PATH_COMMER = os.path.join(BASE_DIR, SILVER_BASE, date_str, 'commerces_paris_silver.parquet')

df_ecoles = pd.read_parquet(PATH_ECOLES)
df_commis = pd.read_parquet(PATH_COMMIS)
df_commer = pd.read_parquet(PATH_COMMER)

print(f"Écoles        : {df_ecoles.shape}")
print(f"Commissariats : {df_commis.shape}")
print(f"Commerces     : {df_commer.shape}")

# ==========================================================================
# 2. AGRÉGATION
# ==========================================================================
df_commer['code_postal'] = df_commer['code_insee'].astype(int) - 100
cols_to_sum = [c for c in df_commer.columns if c not in ['code_insee', 'code_postal', 'commune_nom', 'population_2010']]
df_commer['nb_commerces_total'] = df_commer[cols_to_sum].sum(axis=1)
agg_commer = df_commer[['code_postal', 'nb_commerces_total'] + cols_to_sum].copy()

def agreger_services(df_ecoles, df_commis, group_col):
    dfe = df_ecoles.dropna(subset=[group_col]).copy()
    agg_ecoles = dfe.groupby(group_col).agg(
        nb_ecoles=('etablissement_nom', 'nunique')
    ).reset_index()

    dfc = df_commis.dropna(subset=[group_col]).copy()
    agg_commis = dfc.groupby(group_col).agg(
        nb_commissariats=('commissariat_nom', 'nunique')
    ).reset_index()

    return agg_ecoles.merge(agg_commis, on=group_col, how='outer')

# ==========================================================================
# 3. FUSION ARRONDISSEMENT + QUARTIER
# ==========================================================================
df_arr = agreger_services(df_ecoles, df_commis, 'code_postal')
df_arr = df_arr.merge(agg_commer, on='code_postal', how='outer')
df_arr = df_arr.fillna(0)
cols_int = [c for c in df_arr.columns if c != 'code_postal']
df_arr[cols_int] = df_arr[cols_int].astype(int)
df_arr['code_postal'] = df_arr['code_postal'].astype(int)
df_arr = df_arr.sort_values('code_postal').reset_index(drop=True)

df_quartier = agreger_services(df_ecoles, df_commis, 'code_quartier')
df_quartier = df_quartier.fillna(0)
cols_int_qu = [c for c in df_quartier.columns if c != 'code_quartier']
df_quartier[cols_int_qu] = df_quartier[cols_int_qu].astype(int)
df_quartier['code_quartier'] = df_quartier['code_quartier'].astype(int)

src_noms = pd.concat([
    df_ecoles[['code_quartier', 'nom_quartier', 'code_postal']],
    df_commis[['code_quartier', 'nom_quartier', 'code_postal']],
], ignore_index=True).dropna(subset=['code_quartier'])
src_noms['code_quartier'] = src_noms['code_quartier'].astype(int)
noms_qu = src_noms.drop_duplicates('code_quartier')
df_quartier = df_quartier.merge(noms_qu, on='code_quartier', how='left')
df_quartier = df_quartier.sort_values('code_quartier').reset_index(drop=True)

print(f"\nShape fusion arrondissement : {df_arr.shape}")
print(f"Shape fusion quartier       : {df_quartier.shape}")

# ==========================================================================
# 4. EXPORTS PARQUET
# ==========================================================================
parquet_arr = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_services_quotidien.parquet')
parquet_qu  = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_services_quotidien_quartier.parquet')
df_arr.to_parquet(parquet_arr, index=False)
df_quartier.to_parquet(parquet_qu, index=False)
print(f'\nParquet arrondissement : {parquet_arr}')
print(f'Parquet quartier       : {parquet_qu}')

# ==========================================================================
# 5. POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
        conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_services CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_services_quartier CASCADE;"))
        conn.commit()

    df_arr.to_sql('indicateur_services', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_services ADD PRIMARY KEY (code_postal)"))
        conn.commit()

    df_quartier.to_sql('indicateur_services_quartier', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_services_quartier ADD PRIMARY KEY (code_quartier)"))
        conn.commit()

    print(f'PostgreSQL : silver.indicateur_services ({len(df_arr)} lignes)')
    print(f'PostgreSQL : silver.indicateur_services_quartier ({len(df_quartier)} lignes)')
except Exception as e:
    print(f'PostgreSQL indisponible : {e}')

# ==========================================================================
# 6. MONGODB
# ==========================================================================
print("\n--- INSERTION MONGODB ---")

df_ecoles_geo = df_ecoles.dropna(subset=['lat', 'lon']).copy()
df_ecoles_geo['type'] = 'ecole'
df_ecoles_geo['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(df_ecoles_geo['lon'], df_ecoles_geo['lat'])
]
for c in ['code_quartier', 'nom_quartier']:
    if c not in df_ecoles_geo.columns:
        df_ecoles_geo[c] = None
df_ecoles_geo['code_quartier'] = df_ecoles_geo['code_quartier'].apply(
    lambda v: int(v) if pd.notna(v) else None
)
cols_keep_ecoles = ['code_postal', 'code_quartier', 'nom_quartier', 'etablissement_nom', 'type', 'geo']
ecoles_docs = df_ecoles_geo[cols_keep_ecoles].to_dict(orient='records')

df_commis_geo = df_commis.dropna(subset=['lat', 'lon']).copy()
df_commis_geo['type'] = 'commissariat'
df_commis_geo['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(df_commis_geo['lon'], df_commis_geo['lat'])
]
for c in ['code_quartier', 'nom_quartier']:
    if c not in df_commis_geo.columns:
        df_commis_geo[c] = None
df_commis_geo['code_quartier'] = df_commis_geo['code_quartier'].apply(
    lambda v: int(v) if pd.notna(v) else None
)
cols_keep_commis = ['code_postal', 'code_quartier', 'nom_quartier', 'commissariat_nom', 'type_commissariat', 'type', 'geo']
commis_docs = df_commis_geo[cols_keep_commis].to_dict(orient='records')

def insert_ecoles():
    if ecoles_docs:
        mongo['indicateur_services_geo'].insert_many(ecoles_docs, ordered=False)

def insert_commissariats():
    if commis_docs:
        mongo['indicateur_services_geo'].insert_many(commis_docs, ordered=False)

try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_services_geo'].drop()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_ecoles = executor.submit(insert_ecoles)
        future_commis = executor.submit(insert_commissariats)
        future_ecoles.result()
        future_commis.result()

    mongo['indicateur_services_geo'].create_index([("geo", GEOSPHERE)])
    mongo['indicateur_services_geo'].create_index([("code_postal", 1)])
    mongo['indicateur_services_geo'].create_index([("code_quartier", 1)])
    print(f'MongoDB : {len(ecoles_docs)} écoles + {len(commis_docs)} commissariats insérés')
    print('MongoDB : Index 2dsphere + code_postal + code_quartier créés')
except Exception as e:
    print(f'MongoDB indisponible : {e}')

print('\n=== SILVER FUSION IND4 TERMINÉE ===')