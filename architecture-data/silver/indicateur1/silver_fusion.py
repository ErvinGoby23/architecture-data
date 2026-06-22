"""
silver_fusion.py — Nettoyage & Fusion Indicateur 1 (QUARTIER + ARRONDISSEMENT)
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

cols_arrets = ['code_quartier', 'nom_quartier', 'arrondissement', 'stop_id', 'stop_lat', 'stop_lon', 'route_type', 'route_short_name', 'mode_nom']
cols_taxi   = ['code_quartier', 'nom_quartier', 'arrondissement', 'borne_id', 'lat', 'lon', 'nb_emplacements']
cols_stat   = ['code_quartier', 'nom_quartier', 'arrondissement', 'places_relevees', 'regime_priorite']

df_arrets = df_arrets[[c for c in cols_arrets if c in df_arrets.columns]]
df_taxi   = df_taxi[[c for c in cols_taxi     if c in df_taxi.columns]]
df_stat   = df_stat[[c for c in cols_stat     if c in df_stat.columns]]

# ==========================================================================
# 2. CATÉGORISATION stationnement
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
# 3. FONCTION D'AGRÉGATION GÉNÉRIQUE (quartier ou arrondissement)
# ==========================================================================
def agreger(df_arrets, df_taxi, df_stat, group_col):
    """Agrège les 3 sources sur la colonne group_col (code_quartier ou arrondissement)."""

    # Arrêts
    agg_arrets = df_arrets.groupby(group_col).agg(
        nb_arrets   = ('stop_id',          'nunique'),
        nb_lignes   = ('route_short_name', 'nunique'),
        nb_modes    = ('route_type',       'nunique'),
        modes_liste = ('mode_nom',         lambda x: ', '.join(sorted(set(x.dropna())))),
    ).reset_index()

    if 'mode_nom' in df_arrets.columns:
        modes_count = df_arrets.groupby([group_col, 'mode_nom']).agg(
            nb=('stop_id', 'nunique')
        ).reset_index()
        modes_pivot = modes_count.pivot_table(
            index=group_col,
            columns='mode_nom',
            values='nb',
            fill_value=0
        ).reset_index()
        modes_pivot.columns = [group_col] + [
            f'nb_arrets_{c.lower().replace(" ", "_").replace("é", "e").replace("â", "a")}'
            for c in modes_pivot.columns[1:]
        ]
        agg_arrets = agg_arrets.merge(modes_pivot, on=group_col, how='left')

    # Taxi
    agg_taxi = df_taxi.groupby(group_col).agg(
        nb_bornes            = ('borne_id',        'count'),
        nb_emplacements_taxi = ('nb_emplacements', 'sum'),
    ).reset_index()

    # Stationnement
    agg_stat = df_stat.pivot_table(
        index=group_col,
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

    # Fusion
    df_fusion = agg_arrets.merge(agg_taxi, on=group_col, how='outer')
    df_fusion = df_fusion.merge(agg_stat,  on=group_col, how='outer')
    df_fusion = df_fusion.fillna(0)
    df_fusion = df_fusion.sort_values(group_col).reset_index(drop=True)
    return df_fusion

# ==========================================================================
# 4. AGRÉGATION QUARTIER + ARRONDISSEMENT
# ==========================================================================
print("\n--- AGRÉGATION PAR QUARTIER ---")
df_quartier = agreger(df_arrets, df_taxi, df_stat, 'code_quartier')

# Ajout du nom_quartier dans le résultat quartier
noms_qu = df_arrets[['code_quartier', 'nom_quartier', 'arrondissement']].drop_duplicates('code_quartier')
df_quartier = df_quartier.merge(noms_qu, on='code_quartier', how='left')
print(f"Shape quartier : {df_quartier.shape} ({df_quartier['code_quartier'].nunique()} quartiers)")

print("\n--- AGRÉGATION PAR ARRONDISSEMENT ---")
df_arrondissement = agreger(df_arrets, df_taxi, df_stat, 'arrondissement')
print(f"Shape arrondissement : {df_arrondissement.shape} ({df_arrondissement['arrondissement'].nunique()} arrondissements)")

# ==========================================================================
# 5. EXPORTS PARQUET
# ==========================================================================
parquet_quartier = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_mobilite_quartier_silver.parquet')
df_quartier.to_parquet(parquet_quartier, index=False)
print(f'\n✓ Parquet quartier : {parquet_quartier}')

parquet_arrondissement = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_mobilite_arrondissement_silver.parquet')
df_arrondissement.to_parquet(parquet_arrondissement, index=False)
print(f'✓ Parquet arrondissement : {parquet_arrondissement}')

# ==========================================================================
# 6. POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
        conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_mobilite_quartier CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS silver.indicateur_mobilite_arrondissement CASCADE;"))
        conn.commit()

    df_q_pg  = df_quartier.drop(columns=['modes_liste'], errors='ignore')
    df_ar_pg = df_arrondissement.drop(columns=['modes_liste'], errors='ignore')

    df_q_pg.to_sql('indicateur_mobilite_quartier', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_mobilite_quartier ADD PRIMARY KEY (code_quartier)"))
        conn.commit()

    df_ar_pg.to_sql('indicateur_mobilite_arrondissement', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_mobilite_arrondissement ADD PRIMARY KEY (arrondissement)"))
        conn.commit()

    print(f'✓ PostgreSQL : silver.indicateur_mobilite_quartier ({len(df_q_pg)} lignes)')
    print(f'✓ PostgreSQL : silver.indicateur_mobilite_arrondissement ({len(df_ar_pg)} lignes)')
except Exception as e:
    print(f'❌ PostgreSQL indisponible : {e}')

# ==========================================================================
# 7. MONGODB (points géo inchangés, on ajoute code_quartier + arrondissement)
# ==========================================================================
print("\n--- INSERTION DES DOCUMENTS GÉOMÉTRIQUES DANS MONGODB ---")

df_arrets_valid = df_arrets.dropna(subset=['stop_lat', 'stop_lon']).copy()
arrets_docs = [{
    'code_quartier' : int(r['code_quartier']),
    'nom_quartier'  : r.get('nom_quartier', ''),
    'arrondissement': int(r['arrondissement']),
    'type'          : 'arret',
    'mode_nom'      : r.get('mode_nom', ''),
    'geo'           : {'type': 'Point', 'coordinates': [float(r['stop_lon']), float(r['stop_lat'])]},
} for _, r in df_arrets_valid.iterrows()]

df_taxi_valid = df_taxi.dropna(subset=['lat', 'lon']).copy()
taxi_docs = [{
    'code_quartier' : int(r['code_quartier']),
    'nom_quartier'  : r.get('nom_quartier', ''),
    'arrondissement': int(r['arrondissement']),
    'type'          : 'borne_taxi',
    'geo'           : {'type': 'Point', 'coordinates': [float(r['lon']), float(r['lat'])]},
} for _, r in df_taxi_valid.iterrows()]

df_stat_full = pd.read_parquet(f'{SILVER_BASE}/{date_str}/stationnement_paris_silver.parquet')
df_stat_geo  = df_stat_full.dropna(subset=['latitude', 'longitude']).copy()
stat_docs = [{
    'code_quartier' : int(r['code_quartier']),
    'nom_quartier'  : r.get('nom_quartier', ''),
    'arrondissement': int(r['arrondissement']),
    'type'          : REGIME_MAP.get(r.get('regime_priorite', ''), 'autre'),
    'geo'           : {'type': 'Point', 'coordinates': [float(r['longitude']), float(r['latitude'])]},
} for _, r in df_stat_geo.iterrows()]

def insert_arrets():
    if arrets_docs:
        mongo['indicateur_mobilite'].insert_many(arrets_docs, ordered=False)

def insert_taxi():
    if taxi_docs:
        mongo['indicateur_mobilite'].insert_many(taxi_docs, ordered=False)

def insert_stationnement():
    if stat_docs:
        mongo['indicateur_mobilite'].insert_many(stat_docs, ordered=False)

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

    mongo['indicateur_mobilite'].create_index([("geo", GEOSPHERE)])
    mongo['indicateur_mobilite'].create_index([("code_quartier", 1)])
    mongo['indicateur_mobilite'].create_index([("arrondissement", 1)])
    print(f'✓ MongoDB : {len(arrets_docs) + len(taxi_docs) + len(stat_docs)} documents insérés')
    print('✓ MongoDB : Index 2dsphere + code_quartier + arrondissement créés')
except Exception as e:
    print(f'❌ MongoDB indisponible : {e}')

print('\n=== SILVER mobilité OK ===')