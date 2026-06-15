"""
gold_score_mobilite.py — Pipeline Gold · Indicateur 1 : Score de Mobilité (VERSION SÉCURISÉE)
Urban Data Explorer
"""

import pandas as pd
import numpy as np
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv('../../../.env')

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
SILVER_BASE = os.path.join(ROOT_DIR, 'silver', 'indicateur1', 'nettoyage-indicateur1')

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

print(f"=== GOLD (IND1) — date silver : {date_str} ===")

BRUTE_DIR  = os.path.join(ROOT_DIR, 'brute', 'indicateur-Score-accessibilité-mobilité')
SILVER_DIR = os.path.join(ROOT_DIR, 'silver', 'indicateur1', 'nettoyage-indicateur1', date_str)
GOLD_DIR   = os.path.join(ROOT_DIR, 'gold', 'indicateur1', date_str)

PG_URL = os.getenv('PG_URL')
os.makedirs(GOLD_DIR, exist_ok=True)

# ==========================================================================
# 1. LECTURE SILVER
# ==========================================================================
silver_parquet_path = os.path.join(SILVER_DIR, 'indicateur_mobilite_silver.parquet')

if not os.path.exists(silver_parquet_path):
    raise FileNotFoundError(f"❌ Le fichier Silver recherché est introuvable : {silver_parquet_path}")

df = pd.read_parquet(silver_parquet_path)
print(f"Shape silver : {df.shape}")

# ==========================================================================
# 2. ENRICHISSEMENT PAR LA SURFACE
# ==========================================================================
csv_path    = os.path.join(BRUTE_DIR, 'arrondissements.csv')
df_arr      = pd.read_csv(csv_path, sep=';')
col_surface = next((c for c in df_arr.columns if 'surface' in c.lower()), None)
col_num     = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)

df_surface = df_arr[[col_num, col_surface]].copy()
df_surface.columns = ['arrondissement', 'surface_m2']
df_surface['surface_km2'] = (df_surface['surface_m2'] / 1_000_000).round(4)
df['arrondissement'] = df['code_postal'].astype(int) - 75000
df = df.merge(df_surface, on='arrondissement', how='left')

# ==========================================================================
# 3. INDICATEURS PAR KM²
# ==========================================================================
df['nb_arrets_par_km2']         = (df['nb_arrets']           / df['surface_km2']).round(2)
df['nb_lignes_par_km2']         = (df['nb_lignes']            / df['surface_km2']).round(2)
df['nb_bornes_par_km2']         = (df['nb_bornes']            / df['surface_km2']).round(2)
df['nb_places_gratuit_par_km2'] = (df['nb_places_gratuit']    / df['surface_km2']).round(2)
df['nb_places_2roues_par_km2']  = (df['nb_places_2roues']     / df['surface_km2']).round(2)
df['nb_places_pmr_par_km2']     = (df['nb_places_pmr']        / df['surface_km2']).round(2)
df['nb_places_elec_par_km2']    = (df['nb_places_electrique'] / df['surface_km2']).round(2)

# ==========================================================================
# 4. NORMALISATION MIN-MAX (0 → 1)
# ==========================================================================
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

# ==========================================================================
# 5. SCORE FINAL PONDÉRÉ ET RANG
# ==========================================================================
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

df['score_mobilite_100'] = (df['score_mobilite'] * 100).round(1)
df['rang'] = df['score_mobilite'].rank(ascending=False, method='first').astype(int)

# Vectorisé avec pd.cut au lieu de apply(categorise)
df['categorie'] = pd.cut(
    df['score_mobilite'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=['Peu accessible', 'Accessible', 'Très accessible'],
    include_lowest=True
)

df_gold = df.sort_values('rang').reset_index(drop=True)


# ==========================================================================
# 6. VALIDATION
# ==========================================================================
assert df_gold['score_mobilite'].isna().sum() == 0,   "❌ NaN dans score_mobilite"
assert df_gold['score_mobilite'].between(0, 1).all(), "❌ Score hors [0,1]"
assert len(df_gold) == 20,                            "❌ Nombre d'arrondissements incorrect"
assert df_gold['rang'].nunique() == 20,               "❌ Les rangs ne sont pas uniques"

cols_keep = [
    'code_postal',
    'nb_arrets', 'nb_lignes', 'nb_modes', 'modes_liste',
    'nb_arrets_bus', 'nb_arrets_metro', 'nb_arrets_rer', 'nb_arrets_tram',
    'nb_arrets_train', 'nb_arrets_train_regional', 'nb_arrets_funiculaire',
    'nb_bornes', 'nb_emplacements_taxi',
    'nb_places_2roues', 'nb_places_electrique', 'nb_places_gratuit',
    'nb_places_payant', 'nb_places_pmr',
    'score_arrets', 'score_lignes', 'score_modes', 'score_taxi',
    'score_gratuit', 'score_2roues', 'score_pmr', 'score_electrique',
    'score_mobilite', 'score_mobilite_100',
    'rang', 'categorie'
]
df_gold = df_gold[cols_keep]

# ==========================================================================
# 7. EXPORT PARQUET
# ==========================================================================
parquet_path = os.path.join(GOLD_DIR, 'score_mobilite_gold.parquet')
df_gold.to_parquet(parquet_path, index=False)
print(f'✓ Fichier Parquet daté sauvegardé : {parquet_path}')

# ==========================================================================
# 8. EXPORT POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.score_mobilite CASCADE;"))
        conn.commit()
    df_gold.to_sql('score_mobilite', engine, if_exists='replace', index=False, schema='gold')
    # Ajout PRIMARY KEY
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE gold.score_mobilite ADD PRIMARY KEY (code_postal)"))
        conn.commit()
    print(f'✓ PostgreSQL : table gold.score_mobilite écrasée avec le jour J ({len(df_gold)} lignes)')
    print(f'✓ PostgreSQL : table gold.score_mobilite écrasée avec le jour J ({len(df_gold)} lignes)')
except Exception as e:
    print(f'❌ PostgreSQL indisponible — export ignoré : {e}')
    print('   Le Parquet reste la source canonique.')

print('\n=== GOLD mobilité OK ===')