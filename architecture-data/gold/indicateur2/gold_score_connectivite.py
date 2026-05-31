"""
gold_score_connectivite.py — Pipeline Gold · Indicateur 2 : Score de connectivité
Urban Data Explorer
"""

import pandas as pd
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv('../../../.env')

def get_latest_date(silver_dir):
    dates = sorted([
        d for d in os.listdir(silver_dir)
        if os.path.isdir(os.path.join(silver_dir, d))
    ], reverse=True)
    if not dates:
        raise FileNotFoundError(f"Aucun dossier de date trouvé dans {silver_dir}")
    return dates[0]

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
SILVER_BASE = os.path.join(ROOT_DIR, 'silver', 'indicateur2', 'nettoyage-indicateur2')

if len(sys.argv) > 1:
    date_str = sys.argv[1]
else:
    date_str = get_latest_date(SILVER_BASE)

print(f"=== GOLD (IND2) — date silver : {date_str} ===")

SILVER_DIR = os.path.join(SILVER_BASE, date_str)
GOLD_DIR   = os.path.join(ROOT_DIR, 'gold', 'indicateur2', date_str)
BRUTE_DIR  = os.path.join(ROOT_DIR, 'brute', 'indicateur-Score-accessibilité-mobilité')
PG_URL     = os.getenv('PG_URL')

os.makedirs(GOLD_DIR, exist_ok=True)

# ==========================================================================
# 1. LECTURE SILVER
# ==========================================================================
silver_parquet_path = os.path.join(SILVER_DIR, 'indicateur_connectivite_silver.parquet')

if not os.path.exists(silver_parquet_path):
    raise FileNotFoundError(f"Le fichier Silver est introuvable : {silver_parquet_path}")

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

df = df.merge(df_surface, on='arrondissement', how='left')

# ==========================================================================
# 3. INDICATEURS PAR KM²
# ==========================================================================
df['nb_antennes_par_km2']    = (df['nb_antennes']    / df['surface_km2']).round(2)
df['nb_antennes_5g_par_km2'] = (df['nb_antennes_5g'] / df['surface_km2']).round(2)
df['nb_antennes_4g_par_km2'] = (df['nb_antennes_4g'] / df['surface_km2']).round(2)

df['taux_fibre'] = pd.to_numeric(df['taux_fibre'], errors='coerce')
df['taux_5g']    = pd.to_numeric(df['taux_5g'],    errors='coerce')
df['taux_4g']    = pd.to_numeric(df['taux_4g'],    errors='coerce')

# ==========================================================================
# 4. NORMALISATION MIN-MAX (0 → 1)
# ==========================================================================
def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)

df['score_fibre']   = normalize(df['taux_fibre'])
df['score_mobile']  = normalize(
    df['nb_antennes_5g'] * 4 +
    df['nb_antennes_4g'] * 3 +
    df['nb_antennes_3g'] * 2 +
    df['nb_antennes_2g'] * 1
)
df['score_densite'] = normalize(df['nb_antennes_par_km2'])

# ==========================================================================
# 5. SCORE FINAL PONDÉRÉ ET RANG
# ==========================================================================
df['score_connectivite'] = (
    df['score_fibre']   * 0.45 +
    df['score_mobile']  * 0.40 +
    df['score_densite'] * 0.15
).round(4)

df['score_connectivite_100'] = (df['score_connectivite'] * 100).round(1)
df['rang'] = df['score_connectivite'].rank(ascending=False, method='first').astype(int)

df['categorie'] = pd.cut(
    df['score_connectivite'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=['Peu connecté', 'Connecté', 'Très connecté'],
    include_lowest=True
)

df_gold = df.sort_values('rang').reset_index(drop=True)

# ==========================================================================
# 6. VALIDATION
# ==========================================================================
assert df_gold['score_connectivite'].isna().sum() == 0,   "NaN dans score_connectivite"
assert df_gold['score_connectivite'].between(0, 1).all(), "Score hors [0,1]"
assert len(df_gold) == 20,                                "Nombre d'arrondissements incorrect"
assert df_gold['rang'].nunique() == 20,                   "Les rangs ne sont pas uniques"

print(f"Shape gold : {df_gold.shape}")
print(df_gold[['arrondissement', 'taux_fibre', 'score_mobile', 'score_connectivite_100', 'rang']].to_string(index=False))

# ==========================================================================
# 7. EXPORT PARQUET
# ==========================================================================
parquet_path = os.path.join(GOLD_DIR, 'score_connectivite_gold.parquet')
df_gold.to_parquet(parquet_path, index=False)
print(f'✓ Parquet sauvegardé : {parquet_path}')

# ==========================================================================
# 8. EXPORT POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.score_connectivite CASCADE;"))
        conn.commit()
    df_gold.to_sql('score_connectivite', engine, if_exists='replace', index=False, schema='gold')
    print(f'✓ PostgreSQL : gold.score_connectivite ({len(df_gold)} lignes)')
except Exception as e:
    print(f'PostgreSQL indisponible : {e}')

print('\n=== GOLD connectivite OK ===')