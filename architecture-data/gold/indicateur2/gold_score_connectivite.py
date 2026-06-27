"""
gold_score_connectivite.py — Pipeline Gold · Indicateur 2 : Score de connectivité
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER

Choix méthodologiques :
- Arrondissement : score_fibre (0.45) + score_mobile (0.40) + score_couverture (0.15)
- Quartier : score_mobile (0.70) + score_couverture (0.30)
  → La fibre ARCEP n'est disponible qu'à la maille arrondissement,
    elle est donc exclue du score quartier pour éviter un biais de nivellement intra-arrondissement.
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



# FONCTIONS COMMUNES


def normalize(series):
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)


def calculer_scores(df, niveau='arrondissement'):
    """
    Calcule les scores normalisés et le score final.
    - niveau='arrondissement' : inclut la fibre (donnée native à ce niveau)
    - niveau='quartier'       : exclut la fibre (données héritées = biais de nivellement)
    """
    df = df.copy()

    # Taux métier communs
    df['taux_5g'] = (df['nb_antennes_5g'] / df['nb_antennes'].replace(0, 1) * 100).round(2)
    df['taux_4g'] = (df['nb_antennes_4g'] / df['nb_antennes'].replace(0, 1) * 100).round(2)

    # Densité surfacique (par km²) — pondérée par génération
    df['score_mobile'] = normalize(
        (df['nb_antennes_5g'] * 4 +
         df['nb_antennes_4g'] * 3 +
         df['nb_antennes_3g'] * 2 +
         df['nb_antennes_2g'] * 1) / df['surface_km2']
    )

    # Couverture récente (mix taux 4G + 5G)
    df['score_couverture'] = normalize(df['taux_4g'] + df['taux_5g'])

    if niveau == 'arrondissement':
        df['taux_fibre'] = (
            df['locaux_fibres_T4_2025'] / df['locaux_total'].replace(0, 1) * 100
        ).round(2)
        df['taux_fibre'] = pd.to_numeric(df['taux_fibre'], errors='coerce')
        df['score_fibre'] = normalize(df['taux_fibre'])

        df['score_connectivite'] = (
            df['score_fibre']     * 0.45 +
            df['score_mobile']    * 0.40 +
            df['score_couverture']* 0.15
        ).round(4)

    else:  # quartier — fibre exclue
        df['score_connectivite'] = (
            df['score_mobile']    * 0.70 +
            df['score_couverture']* 0.30
        ).round(4)

    df['score_connectivite_100'] = (df['score_connectivite'] * 100).round(1)
    df['rang'] = df['score_connectivite'].rank(ascending=False, method='first').astype(int)
    df['categorie'] = pd.cut(
        df['score_connectivite'],
        bins=[0, 0.33, 0.66, 1.0],
        labels=['Peu connecté', 'Connecté', 'Très connecté'],
        include_lowest=True
    )
    return df


def exporter(df_gold, table_name, pk_cols, parquet_path, engine):
    df_gold.to_parquet(parquet_path, index=False)
    print(f'✓ Parquet : {parquet_path}')
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
        print(f'✓ PostgreSQL : gold.{table_name} ({len(df_gold)} lignes)')
    except Exception as e:
        print(f'❌ PostgreSQL indisponible pour {table_name} : {e}')



# SURFACE — ARRONDISSEMENTS

csv_arr     = os.path.join(BRUTE_DIR, 'arrondissements.csv')
df_arr_ref  = pd.read_csv(csv_arr, sep=';')
col_surface = next((c for c in df_arr_ref.columns if 'surface' in c.lower()), None)
col_num     = next((c for c in df_arr_ref.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
df_surface_arr = df_arr_ref[[col_num, col_surface]].copy()
df_surface_arr.columns = ['arrondissement', 'surface_m2']
df_surface_arr['surface_km2'] = (df_surface_arr['surface_m2'] / 1_000_000).round(4)

# SURFACE — QUARTIERS
csv_qu = os.path.join(BRUTE_DIR, 'quartiers.csv')
df_qu_ref = pd.read_csv(csv_qu, sep=';')
df_qu_ref.columns = df_qu_ref.columns.str.strip()
col_surface_qu = next((c for c in df_qu_ref.columns if 'surface' in c.lower()), None)
df_surface_qu = df_qu_ref[['C_QU', 'L_QU', 'C_AR', col_surface_qu]].copy()
df_surface_qu.columns = ['code_quartier', 'nom_quartier', 'arrondissement', 'surface_m2']
df_surface_qu['surface_km2'] = (df_surface_qu['surface_m2'] / 1_000_000).round(4)

try:
    engine = create_engine(PG_URL)
except Exception as e:
    engine = None
    print(f'⚠️ PostgreSQL non initialisé : {e}')



# BLOC 1 — ARRONDISSEMENT (avec fibre)

print("\n--- GOLD ARRONDISSEMENT ---")
silver_arr_path = os.path.join(SILVER_DIR, 'indicateur_connectivite_silver.parquet')
if not os.path.exists(silver_arr_path):
    raise FileNotFoundError(f"Silver arrondissement introuvable : {silver_arr_path}")

df_arr = pd.read_parquet(silver_arr_path)
df_arr['arrondissement'] = df_arr['arrondissement'].astype(int)
df_arr = df_arr.merge(df_surface_arr, on='arrondissement', how='left')
df_arr = calculer_scores(df_arr, niveau='arrondissement')

assert df_arr['score_connectivite'].isna().sum() == 0
assert df_arr['score_connectivite'].between(0, 1).all()
assert len(df_arr) == 20, f"Nombre d'arrondissements incorrect : {len(df_arr)}"

cols_arr = [
    'arrondissement',
    'nb_antennes', 'nb_antennes_2g', 'nb_antennes_3g', 'nb_antennes_4g', 'nb_antennes_5g',
    'nb_antennes_orange', 'nb_antennes_sfr', 'nb_antennes_free', 'nb_antennes_bouygues',
    'operateur_leader', 'taux_fibre', 'taux_5g', 'taux_4g',
    'score_fibre', 'score_mobile', 'score_couverture',
    'score_connectivite', 'score_connectivite_100', 'rang', 'categorie'
]
df_arr_gold = df_arr[[c for c in cols_arr if c in df_arr.columns]].sort_values('rang').reset_index(drop=True)

exporter(
    df_arr_gold,
    table_name='score_connectivite',
    pk_cols=['arrondissement'],
    parquet_path=os.path.join(GOLD_DIR, 'score_connectivite_gold.parquet'),
    engine=engine
)



# BLOC 2 — QUARTIER (sans fibre)

print("\n--- GOLD QUARTIER ---")
silver_qu_path = os.path.join(SILVER_DIR, 'indicateur_connectivite_quartier_silver.parquet')
if not os.path.exists(silver_qu_path):
    raise FileNotFoundError(f"Silver quartier introuvable : {silver_qu_path}")

df_qu = pd.read_parquet(silver_qu_path)
df_qu = df_qu.merge(df_surface_qu[['code_quartier', 'surface_km2']], on='code_quartier', how='left')
df_qu = calculer_scores(df_qu, niveau='quartier')

assert df_qu['score_connectivite'].isna().sum() == 0
assert df_qu['score_connectivite'].between(0, 1).all()
assert len(df_qu) == 80, f"❌ Nombre de quartiers incorrect : {len(df_qu)}"
assert df_qu['rang'].nunique() == 80, "❌ Rangs non uniques (quartier)"

cols_qu = [
    'code_quartier', 'nom_quartier', 'arrondissement',
    'nb_antennes', 'nb_antennes_2g', 'nb_antennes_3g', 'nb_antennes_4g', 'nb_antennes_5g',
    'nb_antennes_orange', 'nb_antennes_sfr', 'nb_antennes_free', 'nb_antennes_bouygues',
    'operateur_leader', 'taux_5g', 'taux_4g',
    'score_mobile', 'score_couverture',
    'score_connectivite', 'score_connectivite_100', 'rang', 'categorie'
]
df_qu_gold = df_qu[[c for c in cols_qu if c in df_qu.columns]].sort_values('rang').reset_index(drop=True)

exporter(
    df_qu_gold,
    table_name='score_connectivite_quartier',
    pk_cols=['code_quartier'],
    parquet_path=os.path.join(GOLD_DIR, 'score_connectivite_quartier_gold.parquet'),
    engine=engine
)

print('\n=== GOLD connectivite OK ===')