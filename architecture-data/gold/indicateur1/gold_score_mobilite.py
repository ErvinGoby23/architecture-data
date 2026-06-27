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



# FONCTIONS COMMUNES


def normalize(series):
    """Normalisation min-max → [0, 1]"""
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - min_v) / (max_v - min_v)


def calculer_scores(df, surface_col='surface_km2'):
    """Calcule densités, taux relatifs, scores normalisés et score final pondéré."""

    # Indicateurs par km²
    df['nb_arrets_par_km2']         = (df['nb_arrets']           / df[surface_col]).round(2)
    df['nb_lignes_par_km2']         = (df['nb_lignes']            / df[surface_col]).round(2)
    df['nb_bornes_par_km2']         = (df['nb_bornes']            / df[surface_col]).round(2)
    df['nb_places_gratuit_par_km2'] = (df['nb_places_gratuit']    / df[surface_col]).round(2)
    df['nb_places_2roues_par_km2']  = (df['nb_places_2roues']     / df[surface_col]).round(2)
    df['nb_places_pmr_par_km2']     = (df['nb_places_pmr']        / df[surface_col]).round(2)
    df['nb_places_elec_par_km2']    = (df['nb_places_electrique'] / df[surface_col]).round(2)

    # Taux relatifs au maximum parisien (0 → 100%)
    df['taux_arrets']     = (df['nb_arrets_par_km2']         / df['nb_arrets_par_km2'].max()         * 100).round(1)
    df['taux_lignes']     = (df['nb_lignes_par_km2']          / df['nb_lignes_par_km2'].max()          * 100).round(1)
    df['taux_taxi']       = (df['nb_bornes_par_km2']          / df['nb_bornes_par_km2'].max()          * 100).round(1)
    df['taux_gratuit']    = (df['nb_places_gratuit_par_km2']  / df['nb_places_gratuit_par_km2'].max()  * 100).round(1)
    df['taux_2roues']     = (df['nb_places_2roues_par_km2']   / df['nb_places_2roues_par_km2'].max()   * 100).round(1)
    df['taux_pmr']        = (df['nb_places_pmr_par_km2']      / df['nb_places_pmr_par_km2'].max()      * 100).round(1)
    df['taux_electrique'] = (df['nb_places_elec_par_km2']     / df['nb_places_elec_par_km2'].max()     * 100).round(1)

    # Normalisation min-max
    df['score_arrets']     = normalize(df['nb_arrets_par_km2'])
    df['score_lignes']     = normalize(df['nb_lignes_par_km2'])
    df['score_modes']      = normalize(df['nb_modes'])
    df['score_taxi']       = normalize(df['nb_bornes_par_km2'])
    df['score_gratuit']    = normalize(df['nb_places_gratuit_par_km2'])
    df['score_2roues']     = normalize(df['nb_places_2roues_par_km2'])
    df['score_pmr']        = normalize(df['nb_places_pmr_par_km2'])
    df['score_electrique'] = normalize(df['nb_places_elec_par_km2'])

    # Score final pondéré
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
    df['categorie'] = pd.cut(
        df['score_mobilite'],
        bins=[0, 0.33, 0.66, 1.0],
        labels=['Peu accessible', 'Accessible', 'Très accessible'],
        include_lowest=True
    )

    return df


def exporter(df_gold, table_name, pk_col, parquet_path, engine):
    """Export Parquet + PostgreSQL."""
    df_gold.to_parquet(parquet_path, index=False)
    print(f'✓ Parquet : {parquet_path}')

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
            conn.execute(text(f"DROP TABLE IF EXISTS gold.{table_name} CASCADE;"))
            conn.commit()
        df_gold.to_sql(table_name, engine, if_exists='replace', index=False, schema='gold')
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE gold.{table_name} ADD PRIMARY KEY ({pk_col})"))
            conn.commit()
        print(f'✓ PostgreSQL : gold.{table_name} ({len(df_gold)} lignes)')
    except Exception as e:
        print(f'❌ PostgreSQL indisponible pour {table_name} : {e}')



# LECTURE SURFACE — QUARTIERS

csv_quartiers = os.path.join(BRUTE_DIR, 'quartiers.csv')
df_qu_ref = pd.read_csv(csv_quartiers, sep=';')
df_qu_ref.columns = df_qu_ref.columns.str.strip()

col_surface_qu = next((c for c in df_qu_ref.columns if 'surface' in c.lower()), None)
df_surface_qu = df_qu_ref[['C_QU', 'L_QU', 'C_AR', col_surface_qu]].copy()
df_surface_qu.columns = ['code_quartier', 'nom_quartier', 'arrondissement', 'surface_m2']
df_surface_qu['surface_km2'] = (df_surface_qu['surface_m2'] / 1_000_000).round(4)

# LECTURE SURFACE — ARRONDISSEMENTS
csv_arr = os.path.join(BRUTE_DIR, 'arrondissements.csv')
df_arr_ref  = pd.read_csv(csv_arr, sep=';')
col_surface_arr = next((c for c in df_arr_ref.columns if 'surface' in c.lower()), None)
col_num_arr     = next((c for c in df_arr_ref.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
df_surface_arr = df_arr_ref[[col_num_arr, col_surface_arr]].copy()
df_surface_arr.columns = ['arrondissement', 'surface_m2']
df_surface_arr['surface_km2'] = (df_surface_arr['surface_m2'] / 1_000_000).round(4)


try:
    engine = create_engine(PG_URL)
except Exception as e:
    engine = None
    print(f'⚠️ Moteur PostgreSQL non initialisé : {e}')



# BLOC 1 — SCORE PAR QUARTIER (80 quartiers)

print("\n--- GOLD QUARTIER ---")

silver_qu_path = os.path.join(SILVER_DIR, 'indicateur_mobilite_quartier_silver.parquet')
if not os.path.exists(silver_qu_path):
    raise FileNotFoundError(f"❌ Silver quartier introuvable : {silver_qu_path}")

df_qu = pd.read_parquet(silver_qu_path)
print(f"Shape silver quartier : {df_qu.shape}")

df_qu = df_qu.merge(df_surface_qu[['code_quartier', 'nom_quartier', 'arrondissement', 'surface_km2']],
                    on='code_quartier', how='left', suffixes=('', '_ref'))

# Priorité aux colonnes _ref si nom_quartier/arrondissement absents
for col in ['nom_quartier', 'arrondissement']:
    if f'{col}_ref' in df_qu.columns:
        df_qu[col] = df_qu[col].fillna(df_qu[f'{col}_ref'])
        df_qu = df_qu.drop(columns=[f'{col}_ref'])

df_qu = calculer_scores(df_qu, surface_col='surface_km2')

# Validation
assert df_qu['score_mobilite'].isna().sum() == 0,   "❌ NaN dans score_mobilite (quartier)"
assert df_qu['score_mobilite'].between(0, 1).all(), "❌ Score hors [0,1] (quartier)"
assert len(df_qu) == 80,                            f"❌ Nombre de quartiers incorrect : {len(df_qu)} (attendu 80)"
assert df_qu['rang'].nunique() == 80,               "❌ Rangs non uniques (quartier)"

cols_keep_qu = [
    'code_quartier', 'nom_quartier', 'arrondissement',
    'nb_arrets', 'nb_lignes', 'nb_modes', 'modes_liste',
    'nb_arrets_bus', 'nb_arrets_metro', 'nb_arrets_rer', 'nb_arrets_tram',
    'nb_arrets_train', 'nb_arrets_train_regional', 'nb_arrets_funiculaire',
    'nb_bornes', 'nb_emplacements_taxi',
    'nb_places_2roues', 'nb_places_electrique', 'nb_places_gratuit',
    'nb_places_payant', 'nb_places_pmr',
    'taux_arrets', 'taux_lignes', 'taux_taxi', 'taux_gratuit',
    'taux_2roues', 'taux_pmr', 'taux_electrique',
    'score_arrets', 'score_lignes', 'score_modes', 'score_taxi',
    'score_gratuit', 'score_2roues', 'score_pmr', 'score_electrique',
    'score_mobilite', 'score_mobilite_100', 'rang', 'categorie'
]
df_qu_gold = df_qu[[c for c in cols_keep_qu if c in df_qu.columns]].sort_values('rang').reset_index(drop=True)

exporter(
    df_qu_gold,
    table_name='score_mobilite_quartier',
    pk_col='code_quartier',
    parquet_path=os.path.join(GOLD_DIR, 'score_mobilite_quartier_gold.parquet'),
    engine=engine
)



# BLOC 2 — SCORE PAR ARRONDISSEMENT (20 arrondissements)

print("\n--- GOLD ARRONDISSEMENT ---")

silver_arr_path = os.path.join(SILVER_DIR, 'indicateur_mobilite_arrondissement_silver.parquet')
if not os.path.exists(silver_arr_path):
    raise FileNotFoundError(f"❌ Silver arrondissement introuvable : {silver_arr_path}")

df_arr = pd.read_parquet(silver_arr_path)
print(f"Shape silver arrondissement : {df_arr.shape}")

df_arr = df_arr.merge(df_surface_arr, on='arrondissement', how='left')
df_arr = calculer_scores(df_arr, surface_col='surface_km2')

# Validation
assert df_arr['score_mobilite'].isna().sum() == 0,   "❌ NaN dans score_mobilite (arrondissement)"
assert df_arr['score_mobilite'].between(0, 1).all(), "❌ Score hors [0,1] (arrondissement)"
assert len(df_arr) == 20,                            f"❌ Nombre d'arrondissements incorrect : {len(df_arr)} (attendu 20)"
assert df_arr['rang'].nunique() == 20,               "❌ Rangs non uniques (arrondissement)"

cols_keep_arr = [
    'arrondissement',
    'nb_arrets', 'nb_lignes', 'nb_modes', 'modes_liste',
    'nb_arrets_bus', 'nb_arrets_metro', 'nb_arrets_rer', 'nb_arrets_tram',
    'nb_arrets_train', 'nb_arrets_train_regional', 'nb_arrets_funiculaire',
    'nb_bornes', 'nb_emplacements_taxi',
    'nb_places_2roues', 'nb_places_electrique', 'nb_places_gratuit',
    'nb_places_payant', 'nb_places_pmr',
    'taux_arrets', 'taux_lignes', 'taux_taxi', 'taux_gratuit',
    'taux_2roues', 'taux_pmr', 'taux_electrique',
    'score_arrets', 'score_lignes', 'score_modes', 'score_taxi',
    'score_gratuit', 'score_2roues', 'score_pmr', 'score_electrique',
    'score_mobilite', 'score_mobilite_100', 'rang', 'categorie'
]
df_arr_gold = df_arr[[c for c in cols_keep_arr if c in df_arr.columns]].sort_values('rang').reset_index(drop=True)

exporter(
    df_arr_gold,
    table_name='score_mobilite_arrondissement',
    pk_col='arrondissement',
    parquet_path=os.path.join(GOLD_DIR, 'score_mobilite_arrondissement_gold.parquet'),
    engine=engine
)

print('\n=== GOLD mobilité OK ===')