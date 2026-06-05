"""
silver_fusion.py — Nettoyage & Fusion Indicateur 1 (VERSION DATE-AWARE ADAPTÉE & CORRIGÉE)
Urban Data Explorer · Silver layer
"""

import pandas as pd
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE

load_dotenv('../../../.env')

SILVER_BASE = 'nettoyage-indicateur1'

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

print(f"=== EXÉCUTION DU SCRIPT SILVER POUR LA DATE : {date_str} ===")

SILVER_OUTPUT_DIR = os.path.join(SILVER_BASE, date_str)
os.makedirs(SILVER_OUTPUT_DIR, exist_ok=True)

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver'

# ==========================================================================
# 1. LECTURE Parquet
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")
df_arrets = pd.read_parquet(f'{SILVER_BASE}/{date_str}/arrets_lignes_paris_silver.parquet')
df_taxi   = pd.read_parquet(f'{SILVER_BASE}/{date_str}/bornes_taxi_paris_silver.parquet')
df_stat   = pd.read_parquet(f'{SILVER_BASE}/{date_str}/stationnement_paris_silver.parquet')

print(f"Arrêts        : {df_arrets.shape}")
print(f"Taxi          : {df_taxi.shape}")
print(f"Stationnement : {df_stat.shape}")

cols_arrets = ['code_postal', 'stop_id', 'stop_lat', 'stop_lon', 'route_type', 'route_short_name', 'mode_nom']
cols_taxi   = ['code_postal', 'borne_id', 'lat', 'lon', 'nb_emplacements']
cols_stat   = ['code_postal', 'places_relevees', 'regime_priorite']

df_arrets = df_arrets[[c for c in cols_arrets if c in df_arrets.columns]]
df_taxi   = df_taxi[[c for c in cols_taxi     if c in df_taxi.columns]]
df_stat   = df_stat[[c for c in cols_stat     if c in df_stat.columns]]

# ==========================================================================
# 2. CATÉGORISATION
# ==========================================================================
REGIME_MAP = {
    'PAYANT MIXTE'  : 'payant',
    'PAYANT ROTATIF': 'payant',
    '2 ROUES'       : '2roues',
    'LOCATION'      : '2roues',
    'GIG/GIC'       : 'pmr',
    'GRATUIT'       : 'gratuit',
    'ELECTRIQUE'    : 'electrique',
}
df_stat['regime_category'] = df_stat['regime_priorite'].map(REGIME_MAP)
df_stat = df_stat.rename(columns={'places_relevees': 'nb_places_reelles'})
df_stat = df_stat[df_stat['regime_category'].notna()].copy()

# ==========================================================================
# 3. AGRÉGATIONS
# ==========================================================================
agg_arrets = df_arrets.groupby('code_postal').agg(
    nb_arrets   = ('stop_id',          'nunique'),
    nb_lignes   = ('route_short_name', 'nunique'),
    nb_modes    = ('route_type',       'nunique'),
    modes_liste = ('mode_nom',         lambda x: ', '.join(sorted(set(x.dropna())))),
).reset_index()

if 'mode_nom' in df_arrets.columns:
    modes_count = df_arrets.groupby(['code_postal', 'mode_nom']).agg(
        nb=('stop_id', 'nunique')
    ).reset_index()

    modes_pivot = modes_count.pivot_table(
        index='code_postal',
        columns='mode_nom',
        values='nb',
        fill_value=0
    ).reset_index()
    modes_pivot.columns = ['code_postal'] + [
        f'nb_arrets_{c.lower().replace(" ", "_").replace("é", "e").replace("â", "a")}'
        for c in modes_pivot.columns[1:]
    ]
    agg_arrets = agg_arrets.merge(modes_pivot, on='code_postal', how='left')
    print(f"Colonnes modes : {[c for c in agg_arrets.columns if c.startswith('nb_arrets_')]}")

agg_taxi = df_taxi.groupby('code_postal').agg(
    nb_bornes            = ('borne_id',        'count'),
    nb_emplacements_taxi = ('nb_emplacements', 'sum'),
).reset_index()

agg_stat = df_stat.pivot_table(
    index='code_postal',
    columns='regime_category',
    values='nb_places_reelles',
    aggfunc='sum',
    fill_value=0
).reset_index()
agg_stat.columns.name = None
agg_stat = agg_stat.rename(columns={
    'gratuit'   : 'nb_places_gratuit',
    'payant'    : 'nb_places_payant',
    '2roues'    : 'nb_places_2roues',
    'pmr'       : 'nb_places_pmr',
    'electrique': 'nb_places_electrique',
})
for col in ['nb_places_gratuit', 'nb_places_payant', 'nb_places_2roues', 'nb_places_pmr', 'nb_places_electrique']:
    if col not in agg_stat.columns:
        agg_stat[col] = 0

df_fusion = agg_arrets.merge(agg_taxi, on='code_postal', how='outer')
df_fusion = df_fusion.merge(agg_stat,  on='code_postal', how='outer')
df_fusion = df_fusion.fillna(0)
df_fusion['arrondissement'] = df_fusion['code_postal'].astype(int) - 75000
df_fusion = df_fusion.sort_values('arrondissement').reset_index(drop=True)

print(f"\nShape fusion : {df_fusion.shape}")
print(f"Colonnes : {list(df_fusion.columns)}")

# ==========================================================================
# 4. EXPORTS PARQUET & POSTGRESQL
# ==========================================================================
parquet_path = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_mobilite_silver.parquet')
df_fusion.to_parquet(parquet_path, index=False)
print(f'\n✓ Parquet final sauvegardé dans : {parquet_path}')

try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
        conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_mobilite CASCADE;"))
        conn.commit()
    df_fusion.to_sql('indicateur_mobilite', engine, if_exists='replace', index=False, schema='silver')
    print(f'✓ PostgreSQL : table silver.indicateur_mobilite ({len(df_fusion)} lignes)')
except Exception as e:
    print(f'❌ PostgreSQL indisponible — export ignoré : {e}')
    print('   Le Parquet reste la source canonique.')

# ==========================================================================
# 5. MONGODB
# ==========================================================================
# --- 5.1 Préparation : Arrêts ---
df_arrets_valid = df_arrets.dropna(subset=['stop_lat', 'stop_lon']).copy()
arrets_df_tmp = df_arrets_valid.copy()
arrets_df_tmp['code_postal'] = arrets_df_tmp['code_postal'].astype(int)
arrets_df_tmp['type'] = 'arret'
arrets_df_tmp['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(arrets_df_tmp['stop_lon'], arrets_df_tmp['stop_lat'])
]
cols_keep_arrets = [c for c in ['code_postal', 'type', 'stop_id', 'mode_nom', 'route_short_name', 'geo'] if c in arrets_df_tmp.columns]
arrets_docs = arrets_df_tmp[cols_keep_arrets].to_dict(orient='records')

# --- 5.2 Préparation : Taxis ---
df_taxi_valid = df_taxi.dropna(subset=['lat', 'lon']).copy()
taxi_df_tmp = df_taxi_valid.copy()
taxi_df_tmp['code_postal'] = taxi_df_tmp['code_postal'].astype(int)
taxi_df_tmp['type'] = 'borne_taxi'
taxi_df_tmp['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(taxi_df_tmp['lon'], taxi_df_tmp['lat'])
]
taxi_docs = taxi_df_tmp[['code_postal', 'type', 'borne_id', 'geo']].to_dict(orient='records')

# --- 5.3 Préparation : Stationnement ---
df_stat_full = pd.read_parquet(f'{SILVER_BASE}/{date_str}/stationnement_paris_silver.parquet')
df_stat_geo  = df_stat_full.dropna(subset=['latitude', 'longitude']).copy()
stat_df_tmp = df_stat_geo.copy()
stat_df_tmp['code_postal'] = stat_df_tmp['code_postal'].astype(int)
stat_df_tmp['type'] = stat_df_tmp['regime_priorite'].map(REGIME_MAP).fillna('autre')
stat_df_tmp['geo'] = [
    {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    for lon, lat in zip(stat_df_tmp['longitude'], stat_df_tmp['latitude'])
]
stat_docs = stat_df_tmp[['code_postal', 'type', 'id', 'nom_voie', 'regime_priorite', 'places_relevees', 'geo']].to_dict(orient='records')

# --- 5.4 Fonctions d'insertion optimisées (ordered=False = parallélisme côté Atlas) ---
def insert_arrets():
    if arrets_docs:
        mongo['indicateur_mobilite'].insert_many(arrets_docs, ordered=False)

def insert_taxi():
    if taxi_docs:
        mongo['indicateur_mobilite'].insert_many(taxi_docs, ordered=False)

def insert_stationnement():
    if stat_docs:
        mongo['indicateur_mobilite'].insert_many(stat_docs, ordered=False)

# --- 5.5 Exécution multithréadée + résilience ---
print("--- INSERTION DES DOCUMENTS GEOMETRIQUES PROPRES DANS MONGODB ---")
try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_mobilite'].drop()

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_arrets = executor.submit(insert_arrets)
        future_taxi   = executor.submit(insert_taxi)
        future_stat   = executor.submit(insert_stationnement)
        future_arrets.result()
        future_taxi.result()
        future_stat.result()

    print(f'✓ MongoDB : Arrêts ajoutés ({len(arrets_docs)} documents)')
    print(f'✓ MongoDB : Bornes de taxi ajoutées ({len(taxi_docs)} documents)')
    print(f'✓ MongoDB : Places de stationnement ajoutées ({len(stat_docs)} documents)')
    print(f'✓ MongoDB Atlas : Collection complète mise à jour ({len(arrets_docs) + len(taxi_docs) + len(stat_docs)} documents)')

    # --- 5.6 Index géospatial 2dsphere ---
    mongo['indicateur_mobilite'].create_index([("geo", GEOSPHERE)])
    print('✓ MongoDB : Index 2dsphere créé sur le champ "geo"')
except Exception as e:
    print(f'❌ MongoDB indisponible — export géospatial ignoré : {e}')
    print('   Le Parquet et PostgreSQL restent disponibles.')

print('\n=== SILVER mobilité OK ===')