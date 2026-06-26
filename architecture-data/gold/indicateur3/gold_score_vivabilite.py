"""
gold_score_vivabilite.py — Pipeline Gold · Indicateur 3 : Score de Vivabilite
Urban Data Explorer — Granularite : ARRONDISSEMENT + QUARTIER

Choix methodologiques :
- Arrondissement : score_proprete (0.30) + score_espaces_verts (0.25)
                   + score_criminalite (0.25) + score_no2 (0.20)
- Quartier : score_proprete (0.50) + score_espaces_verts (0.50)
  -> Criminalite (CODGEO commune) et NO2 (2019 par arrondissement)
     non disponibles a la granularite quartier.
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
        raise FileNotFoundError(f"Aucun dossier trouvé dans {silver_dir}")
    return dates[0]

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
SILVER_BASE = os.path.join(ROOT_DIR, 'silver', 'indicateur3', 'nettoyage-indicateur3')

date_str = sys.argv[1] if len(sys.argv) > 1 else get_latest_date(SILVER_BASE)
print(f"=== GOLD (IND3) — date silver : {date_str} ===")

SILVER_DIR = os.path.join(SILVER_BASE, date_str)
GOLD_DIR   = os.path.join(ROOT_DIR, 'gold', 'indicateur3', date_str)
PG_URL     = os.getenv('PG_URL')

os.makedirs(GOLD_DIR, exist_ok=True)


# ==========================================================================
# FONCTIONS
# ==========================================================================

def normalize(series):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - mn) / (mx - mn)


def exporter(df_gold, table_name, pk_cols, parquet_path, engine):
    df_gold.to_parquet(parquet_path, index=False)
    print(f"Parquet : {parquet_path}")
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
            conn.execute(text(f"DROP TABLE IF EXISTS gold.{table_name} CASCADE;"))
            conn.commit()
        df_gold.to_sql(table_name, engine, if_exists='replace', index=False, schema='gold')
        pk = ', '.join(pk_cols)
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE gold.{table_name} ADD PRIMARY KEY ({pk})"))
            conn.commit()
        print(f"PostgreSQL : gold.{table_name} ({len(df_gold)} lignes)")
    except Exception as e:
        print(f"PostgreSQL indisponible pour {table_name} : {e}")


# ==========================================================================
# ENGINE
# ==========================================================================
try:
    engine = create_engine(PG_URL)
except Exception as e:
    engine = None
    print(f"PostgreSQL non initialise : {e}")


# ==========================================================================
# BLOC 1 — ARRONDISSEMENT
# ==========================================================================
print("\n--- GOLD ARRONDISSEMENT ---")

silver_arr_path = os.path.join(SILVER_DIR, 'indicateur_vivabilite_silver.parquet')
if not os.path.exists(silver_arr_path):
    raise FileNotFoundError(f"Silver arrondissement introuvable : {silver_arr_path}")

df_arr = pd.read_parquet(silver_arr_path).fillna(0)
print(f"Shape silver arrondissement : {df_arr.shape}")
print(f"Colonnes disponibles : {list(df_arr.columns)}")

# Score proprete — inverse : plus de signalements = moins bon
if 'nb_signalements' in df_arr.columns:
    df_arr['score_proprete'] = normalize(df_arr['nb_signalements']) * -1 + 1
    df_arr['score_proprete'] = normalize(df_arr['score_proprete'])
    print(f"score_proprete calcule depuis nb_signalements")

# Score espaces verts
if 'surface_totale_m2' in df_arr.columns:
    df_arr['score_espaces_verts'] = normalize(df_arr['surface_totale_m2'])
    print(f"score_espaces_verts calcule depuis surface_totale_m2")
elif 'nb_espaces_verts' in df_arr.columns:
    df_arr['score_espaces_verts'] = normalize(df_arr['nb_espaces_verts'])
    print(f"score_espaces_verts calcule depuis nb_espaces_verts")

# Score criminalite — inverse
taux_cols = [c for c in df_arr.columns if c.startswith('taux_')]
if taux_cols:
    df_arr['taux_crime_global'] = df_arr[taux_cols].mean(axis=1)
    df_arr['score_criminalite'] = normalize(df_arr['taux_crime_global']) * -1 + 1
    df_arr['score_criminalite'] = normalize(df_arr['score_criminalite'])
    print(f"score_criminalite calcule depuis {len(taux_cols)} colonnes taux_*")

# Score NO2 — source : nb_personnes_exposees_no2 par arrondissement (inverse)
if 'nb_personnes_exposees_no2' in df_arr.columns:
    df_arr['score_no2'] = normalize(df_arr['nb_personnes_exposees_no2']) * -1 + 1
    df_arr['score_no2'] = normalize(df_arr['score_no2'])
    print(f"score_no2 calcule depuis nb_personnes_exposees_no2 (2019, par arrondissement)")

POIDS_ARR = {
    'score_proprete'      : 0.30,
    'score_espaces_verts' : 0.25,
    'score_criminalite'   : 0.25,
    'score_no2'           : 0.20,
}
available = {k: v for k, v in POIDS_ARR.items() if k in df_arr.columns}
total_w   = sum(available.values())
print(f"Dimensions disponibles : {list(available.keys())} (poids total={total_w})")

df_arr['score_vivabilite'] = sum(
    df_arr[col] * (w / total_w) for col, w in available.items()
).round(4)

df_arr['score_vivabilite_100'] = (df_arr['score_vivabilite'] * 100).round(1)
df_arr['rang'] = df_arr['score_vivabilite'].rank(ascending=False, method='first').astype(int)
df_arr['categorie'] = pd.cut(
    df_arr['score_vivabilite'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=['Peu vivable', 'Vivable', 'Tres vivable'],
    include_lowest=True
)

assert df_arr['score_vivabilite'].isna().sum() == 0,   "NaN score_vivabilite (arr)"
assert df_arr['score_vivabilite'].between(0, 1).all(), "Score hors [0,1] (arr)"
assert len(df_arr) == 20,                              f"{len(df_arr)} arrondissements (attendu 20)"
assert df_arr['rang'].nunique() == 20,                 "Rangs non uniques (arr)"

cols_id    = ['arrondissement'] + (['insee_pop'] if 'insee_pop' in df_arr.columns else [])
cols_brut  = [c for c in df_arr.columns if c.startswith(('nb_', 'taux_', 'surface_', 'no2_'))]
cols_score = list(available.keys()) + ['score_vivabilite', 'score_vivabilite_100', 'rang', 'categorie']
seen = set()
all_cols = [c for c in cols_id + cols_brut + cols_score
            if c in df_arr.columns and not (c in seen or seen.add(c))]

df_arr_gold = df_arr[all_cols].sort_values('rang').reset_index(drop=True)

print(f"\nTop 5 vivabilite arrondissement :")
print(df_arr_gold[['arrondissement', 'rang', 'score_vivabilite_100', 'categorie']].head(5).to_string(index=False))

exporter(
    df_arr_gold,
    table_name='score_vivabilite_arrondissement',
    pk_cols=['arrondissement'],
    parquet_path=os.path.join(GOLD_DIR, 'score_vivabilite_arrondissement_gold.parquet'),
    engine=engine,
)


# ==========================================================================
# BLOC 2 — QUARTIER
# ==========================================================================
print("\n--- GOLD QUARTIER ---")

silver_qu_path = os.path.join(SILVER_DIR, 'indicateur_vivabilite_quartier_silver.parquet')
if not os.path.exists(silver_qu_path):
    raise FileNotFoundError(f"Silver quartier introuvable : {silver_qu_path}")

df_qu = pd.read_parquet(silver_qu_path).fillna(0)
print(f"Shape silver quartier : {df_qu.shape}")
print(f"Colonnes disponibles : {list(df_qu.columns)}")

# Score proprete quartier — inverse
if 'nb_signalements' in df_qu.columns:
    df_qu['score_proprete'] = normalize(df_qu['nb_signalements']) * -1 + 1
    df_qu['score_proprete'] = normalize(df_qu['score_proprete'])
    print(f"score_proprete calcule depuis nb_signalements")

# Score espaces verts quartier
if 'surface_totale_m2' in df_qu.columns:
    df_qu['score_espaces_verts'] = normalize(df_qu['surface_totale_m2'])
    print(f"score_espaces_verts calcule depuis surface_totale_m2")
elif 'nb_espaces_verts' in df_qu.columns:
    df_qu['score_espaces_verts'] = normalize(df_qu['nb_espaces_verts'])
    print(f"score_espaces_verts calcule depuis nb_espaces_verts")

POIDS_QU = {
    'score_proprete'      : 0.50,
    'score_espaces_verts' : 0.50,
}
available_qu = {k: v for k, v in POIDS_QU.items() if k in df_qu.columns}
total_w_qu   = sum(available_qu.values())
print(f"Dimensions disponibles : {list(available_qu.keys())} (poids total={total_w_qu})")

df_qu['score_vivabilite'] = sum(
    df_qu[col] * (w / total_w_qu) for col, w in available_qu.items()
).round(4)

df_qu['score_vivabilite_100'] = (df_qu['score_vivabilite'] * 100).round(1)
df_qu['rang'] = df_qu['score_vivabilite'].rank(ascending=False, method='first').astype(int)
df_qu['categorie'] = pd.cut(
    df_qu['score_vivabilite'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=['Peu vivable', 'Vivable', 'Tres vivable'],
    include_lowest=True
)
df_qu['dimensions_incluses'] = 'proprete,espaces_verts'
df_qu['dimensions_exclues']  = 'no2,criminalite'

assert df_qu['score_vivabilite'].isna().sum() == 0,   "NaN score_vivabilite (quartier)"
assert df_qu['score_vivabilite'].between(0, 1).all(), "Score hors [0,1] (quartier)"
assert len(df_qu) == 80,                              f"{len(df_qu)} quartiers (attendu 80)"
assert df_qu['rang'].nunique() == 80,                 "Rangs non uniques (quartier)"

cols_qu = [
    'code_quartier', 'nom_quartier', 'arrondissement',
    'nb_signalements', 'nb_espaces_verts', 'surface_totale_m2',
    'score_proprete', 'score_espaces_verts',
    'score_vivabilite', 'score_vivabilite_100', 'rang', 'categorie',
    'dimensions_incluses', 'dimensions_exclues',
]
df_qu_gold = df_qu[[c for c in cols_qu if c in df_qu.columns]].sort_values('rang').reset_index(drop=True)

print(f"\nTop 5 vivabilite quartier :")
print(df_qu_gold[['code_quartier', 'nom_quartier', 'arrondissement',
                   'rang', 'score_vivabilite_100', 'categorie']].head(5).to_string(index=False))

exporter(
    df_qu_gold,
    table_name='score_vivabilite_quartier',
    pk_cols=['code_quartier'],
    parquet_path=os.path.join(GOLD_DIR, 'score_vivabilite_quartier_gold.parquet'),
    engine=engine,
)

print('\n=== GOLD VIVABILITE OK ===')
print(f"Note : score quartier base sur 2/4 dimensions (proprete + espaces verts)")
print(f"       Criminalite et NO2 non disponibles a la granularite quartier")