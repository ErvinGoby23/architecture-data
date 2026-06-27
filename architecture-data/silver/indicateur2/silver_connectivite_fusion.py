"""
silver_connectivite_fusion.py — Pipeline Silver · Indicateur 2 : Connectivité (Fusion)
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER
"""

import pandas as pd
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient, GEOSPHERE

load_dotenv('../../../.env')

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

print(f"=== SILVER FUSION (IND2) — date : {date_str} ===")

SILVER_OUTPUT_DIR = os.path.join(SILVER_BASE, date_str)
os.makedirs(SILVER_OUTPUT_DIR, exist_ok=True)

PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = os.getenv('MONGO_DB', 'urban_data')


# 1. CHARGEMENT

print("--- CHARGEMENT ---")
df_fibre       = pd.read_parquet(f'{SILVER_BASE}/{date_str}/fibre_paris_silver.parquet')
df_antennes    = pd.read_parquet(f'{SILVER_BASE}/{date_str}/antennes_relais_paris_silver.parquet')
df_antennes_qu = pd.read_parquet(f'{SILVER_BASE}/{date_str}/antennes_relais_quartier_paris_silver.parquet')

# Filtre sécurité géo
def _filtre_paris(df: pd.DataFrame) -> pd.DataFrame:
    mask = df['latitude'].between(48.7, 49.0) & df['longitude'].between(2.2, 2.5)
    return df[mask].reset_index(drop=True)

df_antennes    = _filtre_paris(df_antennes)
df_antennes_qu = _filtre_paris(df_antennes_qu)

print(f"Fibre          : {df_fibre.shape}")
print(f"Antennes arr.  : {df_antennes.shape}")
print(f"Antennes qtr.  : {df_antennes_qu.shape}")

POIDS_GENERATION = {'5G': 4, '4G': 3, '3G': 2, '2G': 1}
OPERATEURS = {
    'ORANGE':           'nb_antennes_orange',
    'SFR':              'nb_antennes_sfr',
    'FREE MOBILE':      'nb_antennes_free',
    'BOUYGUES TELECOM': 'nb_antennes_bouygues',
}

def agreger_antennes(df_ant, group_col):
    """Agrège les antennes par group_col (code_postal ou code_quartier)."""
    agg = df_ant.groupby(group_col).agg(
        nb_antennes    = ('code_site', 'count'),
        nb_antennes_2g = ('has_2g',   'sum'),
        nb_antennes_3g = ('has_3g',   'sum'),
        nb_antennes_4g = ('has_4g',   'sum'),
        nb_antennes_5g = ('has_5g',   'sum'),
    ).reset_index()

    # Opérateur leader pondéré
    df_ant = df_ant.copy()
    df_ant['poids'] = df_ant['generation'].map(POIDS_GENERATION).fillna(1)
    operateur_leader = (
        df_ant.groupby([group_col, 'operateur'])['poids']
        .sum().reset_index(name='score_op')
        .sort_values('score_op', ascending=False)
        .groupby(group_col).first().reset_index()[[group_col, 'operateur']]
        .rename(columns={'operateur': 'operateur_leader'})
    )
    agg = agg.merge(operateur_leader, on=group_col, how='left')

    # Pivot opérateurs
    op_pivot = (
        df_ant.groupby([group_col, 'operateur']).size()
        .unstack(fill_value=0).reset_index()
    )
    for op_name, col_name in OPERATEURS.items():
        if op_name in op_pivot.columns:
            op_pivot = op_pivot.rename(columns={op_name: col_name})
        else:
            op_pivot[col_name] = 0
    cols_op = [group_col] + list(OPERATEURS.values())
    op_pivot = op_pivot[[c for c in cols_op if c in op_pivot.columns]]
    agg = agg.merge(op_pivot, on=group_col, how='left')
    return agg


# 2. AGRÉGATION ARRONDISSEMENT

print("\n--- AGRÉGATION ARRONDISSEMENT ---")
agg_antennes_arr = agreger_antennes(df_antennes, 'code_postal')

df_fusion_arr = df_fibre.merge(agg_antennes_arr, on='code_postal', how='left')
df_fusion_arr['arrondissement'] = (df_fusion_arr['code_postal'] - 75000).astype(int)
df_fusion_arr = df_fusion_arr.drop(columns=['code_postal'])
df_fusion_arr = df_fusion_arr.sort_values('arrondissement').reset_index(drop=True)
df_fusion_arr = df_fusion_arr.fillna(0)
print(f"Shape fusion arrondissement : {df_fusion_arr.shape}")


# 3. AGRÉGATION QUARTIER
# Fibre = valeur de l'arrondissement parent (pas de données quartier ARCEP)

print("\n--- AGRÉGATION QUARTIER ---")
agg_antennes_qu = agreger_antennes(df_antennes_qu, 'code_quartier')

# Référentiel quartier → arrondissement pour joindre la fibre
ref_qu = df_antennes_qu[['code_quartier', 'nom_quartier', 'arrondissement']].drop_duplicates('code_quartier')

# Fibre par arrondissement — héritée de l'arrondissement parent
fibre_arr = df_fibre.copy()
fibre_arr['arrondissement'] = fibre_arr['code_postal'] - 75000

df_fusion_qu = agg_antennes_qu.merge(ref_qu, on='code_quartier', how='left')
df_fusion_qu = df_fusion_qu.merge(
    fibre_arr[['arrondissement', 'nb_logements', 'nb_etablissements',
               'locaux_total', 'locaux_fibres_T4_2025']],
    on='arrondissement', how='left'
)
df_fusion_qu = df_fusion_qu.sort_values('code_quartier').reset_index(drop=True)
df_fusion_qu = df_fusion_qu.fillna(0)
print(f"Shape fusion quartier : {df_fusion_qu.shape}")
print(f"Quartiers uniques : {df_fusion_qu['code_quartier'].nunique()}")


# 4. EXPORT PARQUET

parquet_arr = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_connectivite_silver.parquet')
df_fusion_arr.to_parquet(parquet_arr, index=False)
print(f'\n✓ Parquet arrondissement : {parquet_arr}')

parquet_qu = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_connectivite_quartier_silver.parquet')
df_fusion_qu.to_parquet(parquet_qu, index=False)
print(f'✓ Parquet quartier : {parquet_qu}')


# 5. POSTGRESQL

try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS silver;'))
        conn.execute(text('DROP TABLE IF EXISTS silver.indicateur_connectivite CASCADE;'))
        conn.execute(text('DROP TABLE IF EXISTS silver.indicateur_connectivite_quartier CASCADE;'))
        conn.commit()

    df_fusion_arr.to_sql('indicateur_connectivite', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_connectivite ADD PRIMARY KEY (arrondissement)"))
        conn.commit()
    print(f'✓ PostgreSQL : silver.indicateur_connectivite ({len(df_fusion_arr)} lignes)')

    df_fusion_qu.to_sql('indicateur_connectivite_quartier', engine, if_exists='replace', index=False, schema='silver')
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE silver.indicateur_connectivite_quartier ADD PRIMARY KEY (code_quartier)"))
        conn.commit()
    print(f'✓ PostgreSQL : silver.indicateur_connectivite_quartier ({len(df_fusion_qu)} lignes)')
except Exception as e:
    print(f'PostgreSQL indisponible : {e}')


# 6. MONGODB — points géo antennes avec code_quartier + arrondissement

try:
    client = MongoClient(MONGO_URL)
    mongo  = client[MONGO_DB]
    mongo['indicateur_connectivite'].drop()

    # Pandas fait son job : typage vectorisé + extraction
    df_antennes_qu['code_quartier']  = df_antennes_qu['code_quartier'].astype(int)
    df_antennes_qu['arrondissement'] = df_antennes_qu['arrondissement'].astype(int)

    cols = ['code_quartier', 'nom_quartier', 'arrondissement',
            'generation', 'operateur', 'longitude', 'latitude']
    antennes_docs = df_antennes_qu[cols].to_dict(orient='records')

    # Python pur fait son job : construction de la structure GeoJSON
    for doc in antennes_docs:
        doc['type'] = 'antenne'
        doc['geo']  = {
            'type': 'Point',
            'coordinates': [float(doc.pop('longitude')), float(doc.pop('latitude'))]
        }

    if antennes_docs:
        mongo['indicateur_connectivite'].insert_many(antennes_docs, ordered=False)

    mongo['indicateur_connectivite'].create_index([("geo", GEOSPHERE)])
    mongo['indicateur_connectivite'].create_index([("code_quartier", 1)])
    mongo['indicateur_connectivite'].create_index([("arrondissement", 1)])
    print(f'✓ MongoDB : {len(antennes_docs)} documents, index 2dsphere + code_quartier + arrondissement')
except Exception as e:
    print(f'MongoDB indisponible : {e}')

print('\n=== SILVER connectivite OK ===')