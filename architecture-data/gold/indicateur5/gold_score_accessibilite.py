"""
gold_score_accessibilite.py — Pipeline Gold · Indicateur 5 : Accessibilité du logement
Urban Data Explorer — Granularité : ARRONDISSEMENT + QUARTIER

Lit la fusion Silver (indicateur_logement_silver.parquet / *_quartier_silver.parquet)
et calcule un score d'accessibilité (un score élevé = logement plus accessible).

Score (orienté accessibilité) :
    score_prix   = 1 - normalize(prix_m2_median)   (moins cher = plus accessible)
    score_social = normalize(nb_logements)         (plus de social = plus accessible)
    score_revenu = normalize(revenu_median / prix_m2_median)  (capacité d'achat)
- ARRONDISSEMENT : prix 0.40 + social 0.25 + revenu 0.35
- QUARTIER       : prix 0.60 + social 0.40
    (le revenu FILOSOFI n'existe qu'à la maille arrondissement -> exclu du quartier)

Données temporelles : rang + catégorie calculés PAR ANNÉE.
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

print(f"=== GOLD (IND5 - ACCESSIBILITE LOGEMENT) — Date : {date_str} ===")

SILVER_OUTPUT_DIR     = os.path.join(ROOT_DIR, 'silver', 'indicateur5', 'nettoyage-indicateur5', date_str)
SILVER_FUSION_PATH    = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_logement_silver.parquet')
SILVER_FUSION_QU_PATH = os.path.join(SILVER_OUTPUT_DIR, 'indicateur_logement_quartier_silver.parquet')

GOLD_DIR = os.path.join(ROOT_DIR, 'gold', 'indicateur5', date_str)
PG_URL   = os.getenv('PG_URL')

os.makedirs(GOLD_DIR, exist_ok=True)


# ==========================================================================
# FONCTIONS COMMUNES
# ==========================================================================

def normalize(series):
    s = pd.to_numeric(series, errors='coerce')
    min_v, max_v = s.min(), s.max()
    if pd.isna(min_v) or max_v == min_v:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - min_v) / (max_v - min_v)


def rang_categorie_par_annee(df, score_col='score_accessibilite'):
    """Rang (1 = plus accessible) et catégorie calculés au sein de chaque année."""
    df = df.copy()
    df['rang'] = (
        df.groupby('annee')[score_col]
        .rank(ascending=False, method='first')
        .astype('Int64')
    )
    df['categorie'] = pd.cut(
        df[score_col],
        bins=[0, 0.33, 0.66, 1.0],
        labels=['Peu accessible', 'Accessible', 'Très accessible'],
        include_lowest=True,
    )
    return df


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


try:
    engine = create_engine(PG_URL) if PG_URL else None
except Exception as e:
    engine = None
    print(f'Moteur PostgreSQL non initialisé : {e}')


# ==========================================================================
# BLOC 1 - SCORE PAR ARRONDISSEMENT (avec revenus)
# ==========================================================================
print("\n--- GOLD ARRONDISSEMENT ---")

if not os.path.exists(SILVER_FUSION_PATH):
    raise FileNotFoundError(f"Fusion silver arrondissement introuvable : {SILVER_FUSION_PATH}")

df = pd.read_parquet(SILVER_FUSION_PATH)
print(f"Shape fusion silver arrondissement : {df.shape}")

# sous-scores
df['score_prix']   = 1 - normalize(df['prix_m2_median'])
df['score_social'] = normalize(df['nb_logements'])
df['capacite_achat'] = (df['revenu_median'] / df['prix_m2_median']).round(3)
df['score_revenu'] = normalize(df['capacite_achat'])

df['score_accessibilite'] = (
    df['score_prix']   * 0.40 +
    df['score_social'] * 0.25 +
    df['score_revenu'] * 0.35
).round(4)

df['score_accessibilite_100'] = (df['score_accessibilite'] * 100).round(1)
df = rang_categorie_par_annee(df)

df_arr_gold = df.sort_values(['annee', 'rang']).reset_index(drop=True)

# validations (table temporelle : on valide la cohérence, pas un compte fixe)
scored = df_arr_gold['score_accessibilite'].dropna()
assert scored.between(0, 1).all(),         "Score hors [0,1] (arrondissement)"
assert df_arr_gold['cle'].is_unique,       "Clés non uniques (arrondissement)"
assert df_arr_gold['arrondissement'].between(1, 20).all(), "Arrondissement hors 1-20"

cols_keep_arr = [
    'cle', 'arrondissement', 'annee',
    'prix_m2_median', 'prix_m2_moyen', 'nb_ventes', 'surface_mediane',
    'nb_logements', 'nb_plai', 'nb_plus', 'nb_plus_cd', 'nb_pls', 'nb_programmes',
    'revenu_median', 'taux_pauvrete', 'rapport_interdecile',
    'prix_bien_60m2', 'taux_effort_achat',
    'score_prix', 'score_social', 'score_revenu',
    'score_accessibilite', 'score_accessibilite_100',
    'rang', 'categorie',
]
df_arr_gold = df_arr_gold[[c for c in cols_keep_arr if c in df_arr_gold.columns]]

print(f"Shape gold arrondissement : {df_arr_gold.shape}")
apercu = df_arr_gold[df_arr_gold['annee'] == df_arr_gold['annee'].max()]
print(apercu[['cle', 'prix_m2_median', 'score_accessibilite_100', 'rang', 'categorie']].head(10).to_string(index=False))

exporter(
    df_arr_gold,
    table_name='score_accessibilite_logement',
    pk_col='cle',
    parquet_path=os.path.join(GOLD_DIR, 'score_accessibilite_logement_gold.parquet'),
    engine=engine
)


# ==========================================================================
# BLOC 2 - SCORE PAR QUARTIER (sans revenus)
# ==========================================================================
print("\n--- GOLD QUARTIER ---")

if not os.path.exists(SILVER_FUSION_QU_PATH):
    raise FileNotFoundError(f"Fusion silver quartier introuvable : {SILVER_FUSION_QU_PATH}")

df_qu = pd.read_parquet(SILVER_FUSION_QU_PATH)
print(f"Shape fusion silver quartier : {df_qu.shape}")

df_qu['score_prix']   = 1 - normalize(df_qu['prix_m2_median'])
df_qu['score_social'] = normalize(df_qu['nb_logements'])

df_qu['score_accessibilite'] = (
    df_qu['score_prix']   * 0.60 +
    df_qu['score_social'] * 0.40
).round(4)

df_qu['score_accessibilite_100'] = (df_qu['score_accessibilite'] * 100).round(1)
df_qu = rang_categorie_par_annee(df_qu)

df_qu_gold = df_qu.sort_values(['annee', 'rang']).reset_index(drop=True)

scored_qu = df_qu_gold['score_accessibilite'].dropna()
assert scored_qu.between(0, 1).all(), "Score hors [0,1] (quartier)"
assert df_qu_gold['cle'].is_unique,   "Clés non uniques (quartier)"

cols_keep_qu = [
    'cle', 'code_quartier', 'nom_quartier', 'arrondissement', 'annee',
    'prix_m2_median', 'prix_m2_moyen', 'nb_ventes', 'surface_mediane',
    'nb_logements', 'nb_plai', 'nb_plus', 'nb_plus_cd', 'nb_pls', 'nb_programmes',
    'score_prix', 'score_social',
    'score_accessibilite', 'score_accessibilite_100',
    'rang', 'categorie',
]
df_qu_gold = df_qu_gold[[c for c in cols_keep_qu if c in df_qu_gold.columns]]

print(f"Shape gold quartier : {df_qu_gold.shape}")
print(f"Quartiers : {df_qu_gold['code_quartier'].nunique()}")

exporter(
    df_qu_gold,
    table_name='score_accessibilite_logement_quartier',
    pk_col='cle',
    parquet_path=os.path.join(GOLD_DIR, 'score_accessibilite_logement_quartier_gold.parquet'),
    engine=engine
)

print('\n=== GOLD ACCESSIBILITE LOGEMENT OK ===')
