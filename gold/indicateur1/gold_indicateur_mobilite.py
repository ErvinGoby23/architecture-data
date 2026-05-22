import pandas as pd
import numpy as np
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pymongo import MongoClient

load_dotenv('../../.env')

BRUTE     = '../../brute/indicateur-Score-accessibilité-mobilité'
GOLD_DIR  = '../../gold/indicateur1/'
PG_URL    = os.getenv('PG_URL')
MONGO_URL = os.getenv('MONGO_URL')
MONGO_DB  = 'gold'
os.makedirs(GOLD_DIR, exist_ok=True)

engine = create_engine(PG_URL)
df = pd.read_sql('SELECT * FROM silver.indicateur_mobilite', engine)
print(f"Shape : {df.shape}")
print(f"Colonnes : {list(df.columns)}")

df_arr      = pd.read_csv(f'{BRUTE}/arrondissements.csv', sep=';')
col_surface = next((c for c in df_arr.columns if 'surface' in c.lower()), None)
col_num     = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)

df_surface = df_arr[[col_num, col_surface]].copy()
df_surface.columns = ['arrondissement', 'surface_m2']
df_surface['surface_km2'] = df_surface['surface_m2'] / 1_000_000

df = df.merge(df_surface, on='arrondissement', how='left')

df['nb_arrets_par_km2']         = (df['nb_arrets']           / df['surface_km2']).round(2)
df['nb_lignes_par_km2']         = (df['nb_lignes']            / df['surface_km2']).round(2)
df['nb_bornes_par_km2']         = (df['nb_bornes']            / df['surface_km2']).round(2)
df['nb_places_gratuit_par_km2'] = (df['nb_places_gratuit']    / df['surface_km2']).round(2)
df['nb_places_2roues_par_km2']  = (df['nb_places_2roues']     / df['surface_km2']).round(2)
df['nb_places_pmr_par_km2']     = (df['nb_places_pmr']        / df['surface_km2']).round(2)
df['nb_places_elec_par_km2']    = (df['nb_places_electrique'] / df['surface_km2']).round(2)

def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)

df['score_arrets']     = normalize(df['nb_arrets_par_km2'])
df['score_lignes']     = normalize(df['nb_lignes_par_km2'])
df['score_modes']      = normalize(df['nb_modes'])
df['score_taxi']       = normalize(df['nb_bornes_par_km2'])
df['score_gratuit']    = normalize(df['nb_places_gratuit_par_km2'])
df['score_2roues']     = normalize(df['nb_places_2roues_par_km2'])
df['score_pmr']        = normalize(df['nb_places_pmr_par_km2'])
df['score_electrique'] = normalize(df['nb_places_elec_par_km2'])

df['score_mobilite'] = (
    df['score_arrets']     * 0.25 +
    df['score_lignes']     * 0.20 +
    df['score_modes']      * 0.10 +
    df['score_taxi']       * 0.10 +
    df['score_gratuit']    * 0.15 +
    df['score_2roues']     * 0.10 +
    df['score_pmr']        * 0.05 +
    df['score_electrique'] * 0.05
).round(4)

df_gold = df.copy()

print(f"\nShape gold : {df_gold.shape}")
cols = ['arrondissement', 'code_postal', 'surface_km2',
        'nb_arrets_par_km2', 'nb_bornes_par_km2',
        'nb_places_gratuit_par_km2', 'nb_places_2roues_par_km2',
        'score_mobilite']
print(df_gold[cols].sort_values('score_mobilite', ascending=False).to_string(index=False))
print(f"Meilleur   : {df_gold.loc[df_gold['score_mobilite'].idxmax(), 'arrondissement']}e arrondissement")
print(f"Moins bien : {df_gold.loc[df_gold['score_mobilite'].idxmin(), 'arrondissement']}e arrondissement")

parquet_path = GOLD_DIR + 'score_mobilite_gold.parquet'
df_gold.to_parquet(parquet_path, index=False)
print(f'✓ Parquet : {parquet_path}')

with engine.connect() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
    conn.execute(text("DROP TABLE IF EXISTS gold.score_mobilite CASCADE;"))
    conn.commit()

df_gold.to_sql('score_mobilite', engine, if_exists='replace', index=False, schema='gold')
print(f'✓ PostgreSQL : table gold.score_mobilite ({len(df_gold)} lignes)')

client = MongoClient(MONGO_URL)
client.drop_database('gold')
mongo = client[MONGO_DB]
mongo['score_mobilite'].insert_many(df_gold.to_dict(orient='records'))
print(f'✓ MongoDB Atlas : collection score_mobilite ({len(df_gold)} documents)')

print('\n=== GOLD mobilité OK ===')