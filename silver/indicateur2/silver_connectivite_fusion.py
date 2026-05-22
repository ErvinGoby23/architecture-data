"""
silver_connectivite_fusion.py — Pipeline Silver · Indicateur 2 : Score de connectivité (Fusion)
Urban Data Explorer

Sources :
    silver/Score de connectivité/fibre_paris_silver.csv
    silver/Score de connectivité/antennes_paris_silver.csv
    brute/Score de connectivité/antennes-relais.csv  (pour coordonnées MongoDB)

Output  :
    silver/Score de connectivité/indicateur_connectivite_silver.parquet
    PostgreSQL  → silver.indicateur_connectivite
    MongoDB     → urban_data.antennes_detail

Table silver produite :
    code_postal             int     ex: 75001
    code_arrondissement     int     ex: 75101
    arrondissement          int     ex: 1
    nom_arrondissement      str     ex: "Paris 1er Arrondissement"
    nb_logements            int
    nb_etablissements       int
    locaux_total            int
    locaux_fibres_T4_2025   int
    nb_antennes             int
    nb_antennes_4g          int
    nb_antennes_5g          int
    operateur_leader        str

Usage :
    python silver_connectivite_fusion.py
"""

import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient

load_dotenv('../../.env')

# ── Chemins ────────────────────────────────────────────────────────────────
SILVER_DIR    = '../../silver/Score de connectivité/'
BRONZE_ANT    = '../../brute/Score de connectivité/antennes-relais.csv'
FILE_FIBRE    = SILVER_DIR + 'fibre_paris_silver.csv'
FILE_ANTENNES = SILVER_DIR + 'antennes_paris_silver.csv'
FILE_OUT      = SILVER_DIR + 'indicateur_connectivite_silver.parquet'
PG_URL        = os.getenv('PG_URL')
MONGO_URL     = os.getenv('MONGO_URL')
MONGO_DB      = 'silver'

os.makedirs(SILVER_DIR, exist_ok=True)

# ── 1. Chargement ──────────────────────────────────────────────────────────
df_fibre    = pd.read_csv(FILE_FIBRE,    encoding='utf-8-sig')
df_antennes = pd.read_csv(FILE_ANTENNES, encoding='utf-8-sig')
print(f'[1/4] Chargement OK — fibre : {df_fibre.shape} | antennes : {df_antennes.shape}')

# ── 2. Fusion sur code_postal ──────────────────────────────────────────────
df_fusion = df_fibre.merge(
    df_antennes[['code_postal', 'nb_antennes', 'nb_antennes_4g', 'nb_antennes_5g', 'operateur_leader']],
    on='code_postal',
    how='outer'
)

df_fusion['arrondissement'] = df_fusion['code_postal'].astype(int) - 75000
df_fusion = df_fusion.sort_values('code_postal').reset_index(drop=True)
print(f'[2/4] Fusion OK — shape : {df_fusion.shape}')

# ── 3. Export CSV ──────────────────────────────────────────────────────────
df_fusion.to_parquet(FILE_OUT, index=False)
print(f'[3/4] ✓ Parquet : {FILE_OUT}')

# ── 4. Export PostgreSQL ───────────────────────────────────────────────────
engine = create_engine(PG_URL)
with engine.connect() as conn:
    conn.execute(text('CREATE SCHEMA IF NOT EXISTS silver;'))
    conn.execute(text('DROP TABLE IF EXISTS silver.indicateur2 CASCADE;'))
    conn.commit()

df_fusion.to_sql('indicateur2', engine, if_exists='replace', index=False, schema='silver')
print(f'[4/4] ✓ PostgreSQL : silver.indicateur2 ({len(df_fusion)} lignes)')

# ── 5. Export MongoDB (antennes avec coordonnées) ──────────────────────────
df_brut = pd.read_csv(BRONZE_ANT, sep=None, engine='python', encoding='utf-8')
df_brut.columns = df_brut.columns.str.strip().str.replace('\ufeff', '', regex=False)

def normalize_arrondissement(code):
    if 75001 <= code <= 75020:
        return code + 100
    return code

df_brut = df_brut[df_brut['Arrondissement'] != 76007].copy()
df_brut['code_arrondissement'] = df_brut['Arrondissement'].apply(normalize_arrondissement)
df_brut['code_postal']         = df_brut['code_arrondissement'] - 75100 + 75000
df_brut['Opérateur']           = df_brut['Opérateur'].str.upper().str.strip()

def parse_geo_point(val):
    """Parse 'lat, lon' → {'type': 'Point', 'coordinates': [lon, lat]}"""
    try:
        lat, lon = [float(x.strip()) for x in val.split(',')]
        return {'type': 'Point', 'coordinates': [lon, lat]}
    except Exception:
        return None

df_brut['geo'] = df_brut['geo_point_2d'].apply(parse_geo_point)
df_brut_valid  = df_brut[df_brut['geo'].notna()].copy()

df_brut_valid = df_brut_valid.rename(columns={'Code site': 'code_site'})

antennes_docs = [
    {
        'code_postal' : int(r.code_postal),
        'type'        : 'antenne',
        'code_site'   : str(r.code_site),
        'geo'         : r.geo
    }
    for r in df_brut_valid.itertuples()
]

client     = MongoClient(MONGO_URL)
collection = client[MONGO_DB]['indicateur2']
collection.drop()
collection.insert_many(antennes_docs)
print(f'✓ MongoDB : urban_data.indicateur2 ({len(antennes_docs)} documents)')

print('\n=== SILVER connectivité OK ===')
print(df_fusion.to_string(index=False))

