"""
silver_connectivite_fusion.py — Pipeline Silver · Indicateur 2 : Connectivité (Fusion)
Urban Data Explorer
"""

import pandas as pd
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE

load_dotenv('../../../.env')

# ==========================================================================
# GESTION DE LA DATE
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SILVER_BASE = 'nettoyage-indicateur2'

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

print(f"=== EXÉCUTION DU SCRIPT SILVER FUSION (IND2) POUR LA DATE : {date_str} ===")

SILVER_OUTPUT_DIR = os.path.join(SILVER_BASE, date_str)
os.makedirs(SILVER_OUTPUT_DIR, exist_ok=True)

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'silver'

# ==========================================================================
# 1. CHARGEMENT Parquet
# ==========================================================================
print("--- CHARGEMENT DES DONNÉES SILVER ---")
df_fibre    = pd.read_parquet(f'{SILVER_BASE}/{date_str}/fibre_paris_silver.parquet')
df_antennes = pd.read_parquet(f'{SILVER_BASE}/{date_str}/antennes_relais_paris_silver.parquet')

# Filtre de sécurité — coordonnées dans la bbox Paris
df_antennes = df_antennes[
    df_antennes['latitude'].between(48.7, 49.0) &
    df_antennes['longitude'].between(2.2, 2.5)
].copy()

print(f"Fibre    : {df_fibre.shape}")
print(f"Antennes : {df_antennes.shape}")

# ==========================================================================
# 2. AGRÉGATION ANTENNES — vectorisé
# ==========================================================================
agg_antennes = df_antennes.groupby('code_postal').agg(
    nb_antennes    = ('code_site', 'count'),
    nb_antennes_2g = ('has_2g',   'sum'),
    nb_antennes_3g = ('has_3g',   'sum'),
    nb_antennes_4g = ('has_4g',   'sum'),
    nb_antennes_5g = ('has_5g',   'sum'),
).reset_index()

# -- Opérateur leader (pondéré par génération) ----------------------------
POIDS_GENERATION = {'5G': 4, '4G': 3, '3G': 2, '2G': 1}
df_antennes['poids'] = df_antennes['generation'].map(POIDS_GENERATION).fillna(1)

operateur_leader = (
    df_antennes.groupby(['code_postal', 'operateur'])['poids']
    .sum()
    .reset_index(name='score_op')
    .sort_values('score_op', ascending=False)
    .groupby('code_postal')
    .first()
    .reset_index()[['code_postal', 'operateur']]
    .rename(columns={'operateur': 'operateur_leader'})
)

agg_antennes = agg_antennes.merge(operateur_leader, on='code_postal', how='left')

# -- Répartition par opérateur --------------------------------------------
OPERATEURS = {
    'ORANGE':           'nb_antennes_orange',
    'SFR':              'nb_antennes_sfr',
    'FREE MOBILE':      'nb_antennes_free',
    'BOUYGUES TELECOM': 'nb_antennes_bouygues',
}

operateurs_pivot = (
    df_antennes.groupby(['code_postal', 'operateur'])
    .size()
    .unstack(fill_value=0)
    .reset_index()
)

for op_name, col_name in OPERATEURS.items():
    if op_name in operateurs_pivot.columns:
        operateurs_pivot = operateurs_pivot.rename(columns={op_name: col_name})
    else:
        operateurs_pivot[col_name] = 0

cols_op = ['code_postal'] + list(OPERATEURS.values())
operateurs_pivot = operateurs_pivot[cols_op]

agg_antennes = agg_antennes.merge(operateurs_pivot, on='code_postal', how='left')

print(f"Colonnes agg_antennes : {list(agg_antennes.columns)}")

# ==========================================================================
# 3. FUSION FIBRE + ANTENNES — vectorisé
# Silver : agrégation et structuration uniquement, pas de calculs métier
# ==========================================================================
df_fusion = df_fibre.merge(agg_antennes, on='code_postal', how='outer')
df_fusion['arrondissement'] = df_fusion['code_postal'].astype(int) - 75000
df_fusion = df_fusion.sort_values('arrondissement').reset_index(drop=True)
df_fusion = df_fusion.fillna(0)

print(f"\nShape fusion : {df_fusion.shape}")
print(f"Colonnes : {list(df_fusion.columns)}")

# ==========================================================================
# 4. EXPORTS PARQUET & POSTGRESQL
# ==========================================================================
parquet_path = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_connectivite_silver.parquet')
df_fusion.to_parquet(parquet_path, index=False)
print(f'\nParquet final sauvegarde : {parquet_path}')

try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS silver;'))
        conn.execute(text('DROP TABLE IF EXISTS silver.indicateur_connectivite CASCADE;'))
        conn.commit()
    df_fusion.to_sql('indicateur_connectivite', engine, if_exists='replace', index=False, schema='silver')
    print(f'PostgreSQL : silver.indicateur_connectivite ({len(df_fusion)} lignes)')
except Exception as e:
    print(f'PostgreSQL indisponible — export ignore : {e}')
    print('   Le Parquet reste la source canonique.')

# ==========================================================================
# 5. MONGODB — insertion parallèle par chunks
# ==========================================================================
try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_connectivite'].drop()

    antennes_docs = (
        df_antennes.assign(
            code_postal = lambda x: x['code_postal'].astype(int),
            type        = 'antenne',
            geo         = lambda x: [
                {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
                for lon, lat in zip(x['longitude'], x['latitude'])
            ]
        )[['code_postal', 'type', 'code_site', 'generation', 'operateur', 'geo']]
        .to_dict(orient='records')
    )

    def insert_chunk(chunk):
        mongo['indicateur_connectivite'].insert_many(chunk)

    if antennes_docs:
        chunk_size = 500
        chunks = [antennes_docs[i:i+chunk_size] for i in range(0, len(antennes_docs), chunk_size)]
        with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as executor:
            futures = [executor.submit(insert_chunk, chunk) for chunk in chunks]
            for f in futures:
                f.result()

    print(f'MongoDB : silver.indicateur_connectivite ({len(antennes_docs)} documents)')

    mongo['indicateur_connectivite'].create_index([("geo", GEOSPHERE)])
    print('MongoDB : Index 2dsphere cree sur le champ "geo"')
except Exception as e:
    print(f'MongoDB indisponible — export geospatial ignore : {e}')
    print('   Le Parquet et PostgreSQL restent disponibles.')

print('\n=== SILVER connectivite OK ===')