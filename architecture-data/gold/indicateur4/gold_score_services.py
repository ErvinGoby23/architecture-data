"""
gold_score_services.py — Pipeline Gold · Indicateur 4 : Densité de services du quotidien
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER
"""

import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

for _env_candidate in [
    os.path.join(ROOT_DIR, '.env'),
    os.path.join(ROOT_DIR, '..', '.env'),
]:
    if os.path.exists(_env_candidate):
        load_dotenv(_env_candidate)
        print(f".env chargé : {os.path.abspath(_env_candidate)}")
        break
else:
    print("Aucun fichier .env trouvé — variables d'environnement système utilisées si présentes.")

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

print(f"=== GOLD (IND4 - SERVICES) — Date : {date_str} ===")

SILVER_OUTPUT_DIR     = os.path.join(ROOT_DIR, 'silver', 'indicateur4', 'nettoyage-indicateur4', date_str)
SILVER_FUSION_PATH    = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_services_quotidien.parquet')
SILVER_FUSION_QU_PATH = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_services_quotidien_quartier.parquet')

BRUTE_DIR = os.path.join(ROOT_DIR, 'brute', 'indicateur-Score-accessibilité-mobilité')
GOLD_DIR  = os.path.join(ROOT_DIR, 'gold', 'indicateur4', date_str)
PG_URL    = os.getenv('PG_URL')

os.makedirs(GOLD_DIR, exist_ok=True)


# ==========================================================================
# FONCTIONS COMMUNES
# ==========================================================================

def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)


def exporter(df_gold, table_name, pk_col, parquet_path, engine):
    df_gold.to_parquet(parquet_path, index=False)
    print(f'Parquet : {parquet_path}')

    if engine is None:
        print(f'PostgreSQL indisponible pour {table_name} — export ignoré.')
        return

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
            conn.execute(text(f"DROP TABLE IF EXISTS gold.{table_name} CASCADE;"))
            conn.commit()
        df_gold.to_sql(table_name, engine, if_exists='replace', index=False, schema='gold')
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE gold.{table_name} ADD PRIMARY KEY ({pk_col})"))
            conn.commit()
        print(f'PostgreSQL : gold.{table_name} ({len(df_gold)} lignes)')
    except Exception as e:
        print(f'PostgreSQL indisponible pour {table_name} : {e}')


# ==========================================================================
# LECTURE SURFACE - ARRONDISSEMENTS
# ==========================================================================
csv_arr    = os.path.join(BRUTE_DIR, 'arrondissements.csv')
df_arr_ref = pd.read_csv(csv_arr, sep=';')
df_arr_ref.columns = df_arr_ref.columns.str.strip()
col_surface_arr = next((c for c in df_arr_ref.columns if 'surface' in c.lower()), None)
col_num_arr     = next((c for c in df_arr_ref.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
df_surface_arr  = df_arr_ref[[col_num_arr, col_surface_arr]].copy()
df_surface_arr.columns = ['arrondissement', 'surface_m2']
df_surface_arr['surface_km2'] = (df_surface_arr['surface_m2'] / 1_000_000).round(4)

# LECTURE SURFACE - QUARTIERS
csv_quartiers = os.path.join(BRUTE_DIR, 'quartiers.csv')
df_qu_ref     = pd.read_csv(csv_quartiers, sep=';')
df_qu_ref.columns = df_qu_ref.columns.str.strip()
col_surface_qu = next((c for c in df_qu_ref.columns if 'surface' in c.lower()), None)
df_surface_qu  = df_qu_ref[['C_QU', 'L_QU', 'C_AR', col_surface_qu]].copy()
df_surface_qu.columns = ['code_quartier', 'nom_quartier', 'arrondissement', 'surface_m2']
df_surface_qu['surface_km2'] = (df_surface_qu['surface_m2'] / 1_000_000).round(4)


try:
    engine = create_engine(PG_URL)
except Exception as e:
    engine = None
    print(f'Moteur PostgreSQL non initialisé : {e}')


# ==========================================================================
# BLOC 1 - SCORE PAR ARRONDISSEMENT
# ==========================================================================
print("\n--- GOLD ARRONDISSEMENT ---")

if not os.path.exists(SILVER_FUSION_PATH):
    raise FileNotFoundError(f"Fusion silver arrondissement introuvable : {SILVER_FUSION_PATH}")

df = pd.read_parquet(SILVER_FUSION_PATH)
print(f"Shape fusion silver arrondissement : {df.shape}")

df['arrondissement'] = df['code_postal'].astype(int) - 75000
df = df.merge(df_surface_arr, on='arrondissement', how='left')

df['ecoles_par_km2']        = (df['nb_ecoles']          / df['surface_km2']).round(2)
df['commissariats_par_km2'] = (df['nb_commissariats']   / df['surface_km2']).round(2)
df['commerces_par_km2']     = (df['nb_commerces_total'] / df['surface_km2']).round(2)

df['score_ecoles']        = normalize(df['ecoles_par_km2'])
df['score_commissariats'] = normalize(df['commissariats_par_km2'])
df['score_commerces']     = normalize(df['commerces_par_km2'])

df['score_services'] = (
    df['score_commerces']     * 0.40 +
    df['score_ecoles']        * 0.35 +
    df['score_commissariats'] * 0.25
).round(4)

df['score_services_100'] = (df['score_services'] * 100).round(1)
df['rang'] = df['score_services'].rank(ascending=False, method='first').astype(int)
df['categorie'] = pd.cut(
    df['score_services'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=['Faible densité', 'Densité moyenne', 'Forte densité'],
    include_lowest=True
)

df_arr_gold = df.sort_values('rang').reset_index(drop=True)

assert df_arr_gold['score_services'].isna().sum() == 0,   "NaN dans score_services (arrondissement)"
assert df_arr_gold['score_services'].between(0, 1).all(), "Score hors [0,1] (arrondissement)"
assert len(df_arr_gold) == 20,                            f"Nombre d'arrondissements incorrect : {len(df_arr_gold)} (attendu 20)"
assert df_arr_gold['rang'].nunique() == 20,               "Rangs non uniques (arrondissement)"

cols_keep_arr = [
    'code_postal', 'arrondissement',
    'nb_ecoles', 'nb_commissariats', 'nb_commerces_total',
    'supermarche', 'boulangerie', 'epicerie', 'superette',
    'ecoles_par_km2', 'commissariats_par_km2', 'commerces_par_km2',
    'score_ecoles', 'score_commissariats', 'score_commerces',
    'score_services', 'score_services_100',
    'rang', 'categorie'
]
df_arr_gold = df_arr_gold[[c for c in cols_keep_arr if c in df_arr_gold.columns]]

print(f"Shape gold arrondissement : {df_arr_gold.shape}")
print(df_arr_gold[['code_postal', 'score_services_100', 'rang', 'categorie']].to_string(index=False))

exporter(
    df_arr_gold,
    table_name='score_services',
    pk_col='code_postal',
    parquet_path=os.path.join(GOLD_DIR, 'score_services_gold.parquet'),
    engine=engine
)


# ==========================================================================
# BLOC 2 - SCORE PAR QUARTIER
# ==========================================================================
print("\n--- GOLD QUARTIER ---")

if not os.path.exists(SILVER_FUSION_QU_PATH):
    raise FileNotFoundError(f"Fusion silver quartier introuvable : {SILVER_FUSION_QU_PATH}")

df_qu = df_surface_qu[['code_quartier', 'nom_quartier', 'arrondissement', 'surface_km2']].copy()

df_silver_qu = pd.read_parquet(SILVER_FUSION_QU_PATH)
df_qu = df_qu.merge(df_silver_qu, on='code_quartier', how='left')

print(f"Shape fusion silver quartier : {df_silver_qu.shape}")
print(f"Shape après merge référence  : {df_qu.shape}")

df_qu['nb_ecoles']        = df_qu['nb_ecoles'].fillna(0).astype(int)
df_qu['nb_commissariats'] = df_qu['nb_commissariats'].fillna(0).astype(int)

for col in ['nom_quartier', 'arrondissement']:
    if f'{col}_ref' in df_qu.columns:
        df_qu[col] = df_qu[col].fillna(df_qu[f'{col}_ref'])
        df_qu = df_qu.drop(columns=[f'{col}_ref'])

df_qu['ecoles_par_km2']        = (df_qu['nb_ecoles']        / df_qu['surface_km2']).round(2)
df_qu['commissariats_par_km2'] = (df_qu['nb_commissariats'] / df_qu['surface_km2']).round(2)

df_qu['score_ecoles']        = normalize(df_qu['ecoles_par_km2'])
df_qu['score_commissariats'] = normalize(df_qu['commissariats_par_km2'])

df_qu['score_services'] = (
    df_qu['score_ecoles']        * 0.60 +
    df_qu['score_commissariats'] * 0.40
).round(4)

df_qu['score_services_100'] = (df_qu['score_services'] * 100).round(1)
df_qu['rang'] = df_qu['score_services'].rank(ascending=False, method='first').astype(int)
df_qu['categorie'] = pd.cut(
    df_qu['score_services'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=['Faible densité', 'Densité moyenne', 'Forte densité'],
    include_lowest=True
)

df_qu_gold = df_qu.sort_values('rang').reset_index(drop=True)

assert df_qu_gold['score_services'].isna().sum() == 0,   "NaN dans score_services (quartier)"
assert df_qu_gold['score_services'].between(0, 1).all(), "Score hors [0,1] (quartier)"
assert len(df_qu_gold) == 80,                            f"Nombre de quartiers incorrect : {len(df_qu_gold)} (attendu 80)"
assert df_qu_gold['rang'].nunique() == 80,               "Rangs non uniques (quartier)"
print(f"   Quartiers traités : {len(df_qu_gold)}")

cols_keep_qu = [
    'code_quartier', 'nom_quartier', 'arrondissement',
    'nb_ecoles', 'nb_commissariats',
    'ecoles_par_km2', 'commissariats_par_km2',
    'score_ecoles', 'score_commissariats',
    'score_services', 'score_services_100',
    'rang', 'categorie'
]
df_qu_gold = df_qu_gold[[c for c in cols_keep_qu if c in df_qu_gold.columns]]

print(f"Shape gold quartier : {df_qu_gold.shape}")

exporter(
    df_qu_gold,
    table_name='score_services_quartier',
    pk_col='code_quartier',
    parquet_path=os.path.join(GOLD_DIR, 'score_services_quartier_gold.parquet'),
    engine=engine
)

print('\n=== GOLD SERVICES OK ===')