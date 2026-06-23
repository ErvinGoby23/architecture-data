"""
gold_score_services.py — Pipeline Gold · Indicateur 3 : Densité de services du quotidien
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

# La fusion Silver est supposée avoir été faite dans gold-indicateur-services (ou un équivalent Silver unifié)
SILVER_FUSION_PATH = os.path.join(ROOT_DIR, 'silver', 'indicateur4', 'indicateur_services', 'indicateur_services_quotidien.parquet')
# On force la date du jour pour l'export Gold
from datetime import datetime
date_str = datetime.now().strftime('%Y-%m-%d')

print(f"=== GOLD (IND4 - SERVICES) — Date d'export : {date_str} ===")

BRUTE_DIR = os.path.join(ROOT_DIR, 'brute', 'indicateur-Score-accessibilité-mobilité')
GOLD_DIR  = os.path.join(ROOT_DIR, 'gold', 'indicateur4', date_str)
PG_URL    = os.getenv('PG_URL')

os.makedirs(GOLD_DIR, exist_ok=True)

# ==========================================================================
# 1. LECTURE FUSION SILVER
# ==========================================================================
if not os.path.exists(SILVER_FUSION_PATH):
    raise FileNotFoundError(f"❌ Le fichier de fusion recherché est introuvable : {SILVER_FUSION_PATH}")

df = pd.read_parquet(SILVER_FUSION_PATH)
print(f"Shape fusion silver : {df.shape}")

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
# On calcule la densité pour pouvoir comparer équitablement un grand vs un petit arrondissement
df['ecoles_par_km2']       = (df['nb_ecoles'] / df['surface_km2']).round(2)
df['commissariats_par_km2']= (df['nb_commissariats'] / df['surface_km2']).round(2)
df['commerces_par_km2']    = (df['nb_commerces_total'] / df['surface_km2']).round(2)

# ==========================================================================
# 4. NORMALISATION MIN-MAX (0 → 1)
# ==========================================================================
def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)

df['score_ecoles']        = normalize(df['ecoles_par_km2'])
df['score_commissariats'] = normalize(df['commissariats_par_km2'])
df['score_commerces']     = normalize(df['commerces_par_km2'])

# ==========================================================================
# 5. SCORE FINAL PONDÉRÉ ET RANG
# ==========================================================================
# La pondération est un choix métier. Exemple ici : 
# 40% pour les commerces, 35% pour les écoles, 25% pour la sécurité/commissariats.
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

df_gold = df.sort_values('rang').reset_index(drop=True)

# ==========================================================================
# 6. VALIDATION
# ==========================================================================
assert df_gold['score_services'].isna().sum() == 0,   "❌ NaN dans score_services"
assert df_gold['score_services'].between(0, 1).all(), "❌ Score hors [0,1]"
assert len(df_gold) == 20,                            "❌ Nombre d'arrondissements incorrect"
assert df_gold['rang'].nunique() == 20,               "❌ Les rangs ne sont pas uniques"

cols_keep = [
    'code_postal',
    'nb_ecoles', 'nb_commissariats', 'nb_commerces_total',
    'supermarche', 'boulangerie', 'epicerie', 'superette', # Exemples de détails conservés
    'ecoles_par_km2', 'commissariats_par_km2', 'commerces_par_km2',
    'score_ecoles', 'score_commissariats', 'score_commerces',
    'score_services', 'score_services_100',
    'rang', 'categorie'
]

# Filtrage dynamique (au cas où certaines colonnes de détail n'existeraient pas)
df_gold = df_gold[[c for c in cols_keep if c in df_gold.columns]]

print(f"\nShape gold final : {df_gold.shape}")
print(df_gold[['code_postal', 'score_services_100', 'rang', 'categorie']].to_string(index=False))

# ==========================================================================
# 7. EXPORT PARQUET
# ==========================================================================
parquet_path = os.path.join(GOLD_DIR, 'score_services_gold.parquet')
df_gold.to_parquet(parquet_path, index=False)
print(f'\n✓ Fichier Parquet Gold sauvegardé : {parquet_path}')

# ==========================================================================
# 8. EXPORT POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.score_services CASCADE;"))
        conn.commit()
        
    df_gold.to_sql('score_services', engine, if_exists='replace', index=False, schema='gold')
    
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE gold.score_services ADD PRIMARY KEY (code_postal)"))
        conn.commit()
    print(f'✓ PostgreSQL : table gold.score_services écrasée avec succès ({len(df_gold)} lignes)')
except Exception as e:
    print(f'❌ PostgreSQL indisponible — export ignoré : {e}')
    print('   Le Parquet reste la source canonique.')

print('\n=== GOLD SERVICES OK ===')