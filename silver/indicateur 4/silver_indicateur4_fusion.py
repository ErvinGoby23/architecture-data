"""
silver_indicateur4_fusion.py — Pipeline Silver · Indicateur 4 : Score de sécurité / équipements (Fusion)
Urban Data Explorer

Sources :
    silver/indicateur4/nettoyage-commissariats/commissariats_silver.csv
    silver/indicateur4/nettoyage-ecoles/ecoles_elementaires_silver.csv
    silver/indicateur4/nettoyage-commerces/commerces_silver.csv

Output :
    silver/indicateur4/indicateur4_silver.parquet
    PostgreSQL  → silver.indicateur4
    MongoDB     → silver.indicateur4

Table silver produite :
    arrondissement          int     ex: 1
    code_postal             int     ex: 75001
    population_2010         int
    nb_commissariats        int
    nb_ecoles               int
    nb_elementaires         int
    nb_polyvalents          int
    total_commerces         int
    densite_commerciale     float
    [23 colonnes commerces détaillées]

Usage :
    python silver_indicateur4_fusion.py
"""

import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient

load_dotenv('../../.env')

# ── Chemins ────────────────────────────────────────────────────────────────
SILVER_DIR    = './'
FILE_COMM     = SILVER_DIR + 'nettoyage-commissariats/commissariats_silver.csv'
FILE_ECO      = SILVER_DIR + 'nettoyage-ecoles/ecoles_elementaires_silver.csv'
FILE_COM      = SILVER_DIR + 'nettoyage-commerces/commerces_silver.csv'
FILE_OUT      = SILVER_DIR + 'indicateur4_silver.parquet'
PG_URL        = os.getenv('PG_URL')
MONGO_URL     = os.getenv('MONGO_URL')
MONGO_DB      = 'silver'

os.makedirs(SILVER_DIR, exist_ok=True)

COMMERCE_COLS = [
    'hypermarche', 'supermarche', 'grande_surface_de_bricolage',
    'superette', 'epicerie', 'boulangerie', 'boucherie_charcuterie',
    'produits_surgeles', 'poissonnerie', 'librairie_papeterie_journaux',
    'magasin_de_vetements', 'magasin_d_equipements_du_foyer',
    'magasin_de_chaussures', 'magasin_d_electromenager_et_de_mat_audio_video',
    'magasin_de_meubles', 'magasin_d_articles_de_sports_et_de_loisirs',
    'magasin_de_revetements_murs_et_sols', 'droguerie_quincaillerie_bricolage',
    'parfumerie', 'horlogerie_bijouterie', 'fleuriste',
    'magasin_d_optique', 'station_service',
]

# ── 1. Chargement ──────────────────────────────────────────────────────────
df_comm = pd.read_csv(FILE_COMM, sep=';', encoding='utf-8-sig')
df_eco  = pd.read_csv(FILE_ECO,  sep=';', encoding='utf-8-sig')
df_com  = pd.read_csv(FILE_COM,  sep=';', encoding='utf-8-sig')
print(f'[1/5] Chargement OK — commissariats : {df_comm.shape} | écoles : {df_eco.shape} | commerces : {df_com.shape}')

# ── 2. Agrégations par arrondissement ─────────────────────────────────────
agg_comm = df_comm.groupby('arrondissement').agg(
    nb_commissariats = ('nom', 'count'),
).reset_index()

agg_eco = df_eco.groupby('arrondissement').agg(
    nb_ecoles       = ('nom',                'count'),
    nb_elementaires = ('type_etablissement', lambda x: (x == 'Élémentaire').sum()),
    nb_polyvalents  = ('type_etablissement', lambda x: (x == 'Polyvalent').sum()),
).reset_index()

agg_com_base  = df_com.groupby('arrondissement').agg(
    population_2010 = ('population_2010', 'sum'),
    total_commerces = ('total_commerces', 'sum'),
).reset_index()
agg_com_types = df_com.groupby('arrondissement')[COMMERCE_COLS].sum().reset_index()
agg_com = agg_com_base.merge(agg_com_types, on='arrondissement', how='outer')

# ── 3. Fusion sur arrondissement ───────────────────────────────────────────
df_fusion = agg_comm.merge(agg_eco, on='arrondissement', how='outer')
df_fusion = df_fusion.merge(agg_com, on='arrondissement', how='outer')
df_fusion = df_fusion.fillna(0)

df_fusion['arrondissement'] = df_fusion['arrondissement'].astype(int)
df_fusion['code_postal']    = df_fusion['arrondissement'] + 75000
df_fusion['densite_commerciale'] = (
    df_fusion['total_commerces'] /
    df_fusion['population_2010'].replace(0, float('nan'))
) * 1000
df_fusion = df_fusion.sort_values('arrondissement').reset_index(drop=True)

print(f'[2/5] Fusion OK — shape : {df_fusion.shape}')

# ── 3. Export Parquet ──────────────────────────────────────────────────────
df_fusion.to_parquet(FILE_OUT, index=False)
print(f'[3/5] ✓ Parquet : {FILE_OUT}')

# ── 4. Export PostgreSQL ───────────────────────────────────────────────────
engine = create_engine(PG_URL)
with engine.connect() as conn:
    conn.execute(text('CREATE SCHEMA IF NOT EXISTS silver;'))
    conn.execute(text('DROP TABLE IF EXISTS silver.indicateur4 CASCADE;'))
    conn.commit()

df_fusion.to_sql('indicateur4', engine, if_exists='replace', index=False, schema='silver')
print(f'[4/5] ✓ PostgreSQL : silver.indicateur4 ({len(df_fusion)} lignes)')

# ── 5. Export MongoDB (commissariats + écoles avec coordonnées) ────────────
def make_geo_point(lon, lat):
    try:
        return {'type': 'Point', 'coordinates': [float(lon), float(lat)]}
    except Exception:
        return None

df_comm['geo'] = df_comm.apply(lambda r: make_geo_point(r['lon'], r['lat']), axis=1)
df_eco['geo']  = df_eco.apply(lambda r: make_geo_point(r['lon'], r['lat']),  axis=1)

df_comm_valid = df_comm[df_comm['geo'].notna()].copy()
df_eco_valid  = df_eco[df_eco['geo'].notna()].copy()

comm_docs = [
    {
        'arrondissement' : int(r.arrondissement),
        'code_postal'    : int(r.arrondissement) + 75000,
        'type'           : 'commissariat',
        'nom'            : r.nom,
        'geo'            : r.geo,
    }
    for r in df_comm_valid.itertuples()
]

eco_docs = [
    {
        'arrondissement'    : int(r.arrondissement),
        'code_postal'       : int(r.arrondissement) + 75000,
        'type'              : 'ecole',
        'nom'               : r.nom,
        'type_etablissement': r.type_etablissement,
        'geo'               : r.geo,
    }
    for r in df_eco_valid.itertuples()
]

docs_mongo = comm_docs + eco_docs

client     = MongoClient(MONGO_URL)
collection = client[MONGO_DB]['indicateur4']
collection.drop()
collection.insert_many(docs_mongo)
print(f'[5/5] ✓ MongoDB : silver.indicateur4 ({len(docs_mongo)} documents)')
print(f'         dont commissariats : {len(comm_docs)}')
print(f'         dont écoles        : {len(eco_docs)}')

print('\n=== SILVER indicateur4 OK ===')
print(df_fusion[['arrondissement', 'nb_commissariats', 'nb_ecoles', 'total_commerces', 'densite_commerciale']].to_string(index=False))
