"""
gold_score_vivabilite.py — Pipeline Gold · Score de Vivabilité
Architecture Data Paris

Granularités produites :
  - ARRONDISSEMENT (20) : toutes les dimensions
      score_proprete, score_espaces_verts, score_criminalite,
      score_bruit, score_no2, score_vivabilite
  - QUARTIER (80) : dimensions géolocalisables uniquement
      score_proprete, score_espaces_verts
      (bruit, NO2 = valeur globale ; criminalité = arrondissement uniquement)

Fichiers silver lus :
  - vivabilite_arrondissement_silver.parquet  (silver_fusion_vivabilite.py)
  - proprete_long_silver.parquet             (silver_proprete.py — lat/lon)
  - espaces_verts_long_silver.parquet        (silver_espaces_verts.py — lat/lon)

Référentiel quartiers :
  - architecture-data/brute/indicateur-Score-accessibilité-mobilité/quartiers.csv
"""

import pandas as pd
import numpy as np
import os
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))

load_dotenv(os.path.join(ROOT_DIR, '.env'))
SILVER_DIR    = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
GOLD_DIR      = os.path.join(ROOT_DIR, 'architecture-data', 'gold', 'indicateur3')
QUARTIERS_CSV = os.path.join(ROOT_DIR, 'architecture-data', 'brute',
                             'indicateur-Score-accessibilité-mobilité',
                             'quartiers.csv')

PG_URL = os.getenv('PG_URL')

# --------------------------------------------------------------------------
# Pondérations score vivabilité quartier (bruit + NO2 + criminalité absents)
# Poids ramenés à 1.0 sur les 2 dimensions disponibles
# --------------------------------------------------------------------------
POIDS_QUARTIER = {
    'score_proprete'      : 0.50,
    'score_espaces_verts' : 0.50,
}
assert abs(sum(POIDS_QUARTIER.values()) - 1.0) < 1e-9

print("=== GOLD Vivabilité ===")

os.makedirs(GOLD_DIR, exist_ok=True)


# ==========================================================================
# FONCTIONS
# ==========================================================================

def normalize_0_1(series):
    """Min-max → [0, 1]."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series), index=series.index)
    return ((series - mn) / (mx - mn)).round(4)


def normalize_100(series, inverse=False):
    """Min-max → [0, 100]. inverse=True si valeur haute = mauvais."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 100
    return (100 - norm if inverse else norm).round(2)


def exporter(df_gold, table_name, pk_col, parquet_path, engine):
    """Export Parquet + PostgreSQL."""
    df_gold.to_parquet(parquet_path, index=False)
    print(f'✓ Parquet : {parquet_path}')

    if engine is None:
        print('⚠️  PostgreSQL ignoré (engine non initialisé)')
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
        print(f'✓ PostgreSQL : gold.{table_name} ({len(df_gold)} lignes)')
    except Exception as e:
        print(f'❌ PostgreSQL indisponible pour {table_name} : {e}')


# ==========================================================================
# RÉFÉRENTIEL QUARTIERS — GeoDataFrame
# ==========================================================================
print("\n--- RÉFÉRENTIEL QUARTIERS ---")

df_qu_ref = pd.read_csv(QUARTIERS_CSV, sep=';')
df_qu_ref.columns = df_qu_ref.columns.str.strip()
df_qu_ref = df_qu_ref.rename(columns={
    'C_QU'   : 'code_quartier',
    'L_QU'   : 'nom_quartier',
    'C_AR'   : 'arrondissement',
    'SURFACE': 'surface_m2',
})
df_qu_ref['surface_km2'] = (df_qu_ref['surface_m2'] / 1_000_000).round(4)

# Parsing GeoJSON → GeoDataFrame
gdf_quartiers = gpd.GeoDataFrame(
    df_qu_ref[['code_quartier', 'nom_quartier', 'arrondissement', 'surface_km2']],
    geometry=gpd.GeoSeries.from_wkt(
        df_qu_ref['Geometry'].apply(
            lambda s: __import__('shapely').wkt.dumps(__import__('shapely').geometry.shape(__import__('json').loads(s)))
            if pd.notna(s) else None
        )
    ),
    crs='EPSG:4326'
)
gdf_quartiers = gdf_quartiers.dropna(subset=['geometry'])
print(f"Quartiers avec géométrie : {len(gdf_quartiers)}/80")


def assigner_quartier(df_points, lat_col='latitude', lon_col='longitude'):
    """Spatial join vectorisé via geopandas — beaucoup plus rapide que la boucle Shapely."""
    gdf_pts = gpd.GeoDataFrame(
        df_points.reset_index(drop=True),
        geometry=gpd.points_from_xy(df_points[lon_col], df_points[lat_col]),
        crs='EPSG:4326'
    )
    joined = gpd.sjoin(gdf_pts, gdf_quartiers[['code_quartier', 'nom_quartier', 'arrondissement', 'geometry']],
                       how='left', predicate='within')
    # Supprimer colonnes geopandas inutiles
    joined = joined.drop(columns=['geometry', 'index_right'], errors='ignore')
    return pd.DataFrame(joined)


# ==========================================================================
# MOTEUR POSTGRESQL
# ==========================================================================
try:
    engine = create_engine(PG_URL)
except Exception as e:
    engine = None
    print(f'⚠️ Moteur PostgreSQL non initialisé : {e}')


# ==========================================================================
# BLOC 1 — SCORE PAR ARRONDISSEMENT (20)
# ==========================================================================
print("\n--- GOLD ARRONDISSEMENT ---")

silver_arr_path = os.path.join(SILVER_DIR, 'vivabilite_arrondissement_silver.parquet')
if not os.path.exists(silver_arr_path):
    raise FileNotFoundError(f"❌ Silver arrondissement introuvable : {silver_arr_path}")

df_arr = pd.read_parquet(silver_arr_path)
print(f"Shape silver arrondissement : {df_arr.shape}")

SCORE_COLS = ['score_proprete', 'score_espaces_verts', 'score_criminalite',
              'score_bruit', 'score_no2', 'score_vivabilite']
manquantes = [c for c in SCORE_COLS if c not in df_arr.columns]
if manquantes:
    raise ValueError(f"❌ Colonnes manquantes dans le silver : {manquantes}")

df_arr['score_vivabilite_01']  = normalize_0_1(df_arr['score_vivabilite'])
df_arr['score_vivabilite_100'] = df_arr['score_vivabilite'].round(1)
df_arr['rang'] = df_arr['score_vivabilite'].rank(ascending=False, method='first').astype(int)
df_arr['categorie'] = pd.cut(
    df_arr['score_vivabilite'],
    bins=[0, 33, 66, 100],
    labels=['Peu vivable', 'Vivable', 'Très vivable'],
    include_lowest=True
)
df_arr['bruit_varie_par_arr'] = False
df_arr['no2_varie_par_arr']   = False

cols_id   = ['arrondissement'] + (['insee_pop'] if 'insee_pop' in df_arr.columns else [])
cols_brut = [c for c in df_arr.columns if c.startswith(('nb_', 'taux_', 'surface_', 'bruit_', 'no2_'))]
cols_fin  = SCORE_COLS + ['score_vivabilite_01', 'score_vivabilite_100', 'rang', 'categorie']

all_cols = cols_id + cols_brut + cols_fin
# Dédoublonnage en conservant l'ordre
seen = set()
all_cols = [c for c in all_cols if c in df_arr.columns and not (c in seen or seen.add(c))]

df_arr_gold = df_arr[all_cols].sort_values('rang').reset_index(drop=True)

assert df_arr_gold['score_vivabilite'].isna().sum() == 0,       "❌ NaN score_vivabilite (arr)"
assert df_arr_gold['score_vivabilite'].between(0, 100).all(),   "❌ Score hors [0,100] (arr)"
assert len(df_arr_gold) == 20,                                  f"❌ {len(df_arr_gold)} arrondissements (attendu 20)"
assert df_arr_gold['rang'].nunique() == 20,                     "❌ Rangs non uniques (arr)"

print(f"\nTop 5 vivabilité :")
print(df_arr_gold[['arrondissement', 'rang', 'score_vivabilite_100', 'categorie']].head(5).to_string(index=False))

exporter(
    df_arr_gold,
    table_name='score_vivabilite_arrondissement',
    pk_col='arrondissement',
    parquet_path=os.path.join(GOLD_DIR, 'score_vivabilite_arrondissement_gold.parquet'),
    engine=engine
)


# ==========================================================================
# BLOC 2 — SCORE PAR QUARTIER (80) — propreté + espaces verts uniquement
# ==========================================================================
print("\n--- GOLD QUARTIER (spatial join) ---")

# --- Propreté : agrégation par quartier via lat/lon ---
prop_long_path = os.path.join(SILVER_DIR, 'proprete_long_silver.parquet')
if not os.path.exists(prop_long_path):
    raise FileNotFoundError(f"❌ Silver propreté long introuvable : {prop_long_path}")

df_prop = pd.read_parquet(prop_long_path)
df_prop = df_prop.dropna(subset=['latitude', 'longitude'])
print(f"Signalements propreté avec coords : {len(df_prop):,}")

print("  → Spatial join propreté...")
df_prop = assigner_quartier(df_prop)
df_prop_ok = df_prop.dropna(subset=['code_quartier'])
print(f"  Signalements assignés à un quartier : {len(df_prop_ok):,} / {len(df_prop):,}")

agg_prop_qu = df_prop_ok.groupby('code_quartier').agg(
    nb_signalements   = ('id_declaration', 'count'),
    score_poids_total = ('poids',          'sum'),
    poids_moyen       = ('poids',          'mean'),
).reset_index()

# --- Espaces verts : agrégation par quartier via lat/lon ---
ev_long_path = os.path.join(SILVER_DIR, 'espaces_verts_long_silver.parquet')
if not os.path.exists(ev_long_path):
    raise FileNotFoundError(f"❌ Silver espaces verts long introuvable : {ev_long_path}")

df_ev = pd.read_parquet(ev_long_path)
df_ev = df_ev.dropna(subset=['latitude', 'longitude'])
print(f"Espaces verts avec coords : {len(df_ev):,}")

print("  → Spatial join espaces verts...")
df_ev = assigner_quartier(df_ev)
df_ev_ok = df_ev.dropna(subset=['code_quartier'])
print(f"  Espaces verts assignés à un quartier : {len(df_ev_ok):,} / {len(df_ev):,}")

agg_ev_col = {'id_espace_vert': 'count'}
if 'surface_m2' in df_ev_ok.columns:
    agg_ev_col['surface_m2'] = 'sum'

agg_ev_qu = df_ev_ok.groupby('code_quartier').agg(**{
    'nb_espaces_verts': pd.NamedAgg('id_espace_vert', 'count'),
    **({'surface_totale_m2': pd.NamedAgg('surface_m2', 'sum')} if 'surface_m2' in df_ev_ok.columns else {})
}).reset_index()

# --- Fusion sur la base des 80 quartiers ---
df_qu_gold = df_qu_ref[['code_quartier', 'nom_quartier', 'arrondissement', 'surface_km2']].copy()
df_qu_gold = df_qu_gold.merge(agg_prop_qu, on='code_quartier', how='left')
df_qu_gold = df_qu_gold.merge(agg_ev_qu,   on='code_quartier', how='left')
df_qu_gold = df_qu_gold.fillna(0)

# --- Scores normalisés 0–100 ---
df_qu_gold['score_proprete'] = normalize_100(
    df_qu_gold['score_poids_total'], inverse=True   # plus de signalements = moins propre
)

if 'surface_totale_m2' in df_qu_gold.columns:
    df_qu_gold['score_espaces_verts'] = normalize_100(df_qu_gold['surface_totale_m2'])
else:
    df_qu_gold['score_espaces_verts'] = normalize_100(df_qu_gold['nb_espaces_verts'])

# --- Score vivabilité quartier (2 dimensions disponibles) ---
df_qu_gold['score_vivabilite'] = sum(
    df_qu_gold[col] * w for col, w in POIDS_QUARTIER.items()
).round(2)

df_qu_gold['score_vivabilite_01']  = normalize_0_1(df_qu_gold['score_vivabilite'])
df_qu_gold['score_vivabilite_100'] = df_qu_gold['score_vivabilite'].round(1)
df_qu_gold['rang'] = df_qu_gold['score_vivabilite'].rank(ascending=False, method='first').astype(int)
df_qu_gold['categorie'] = pd.cut(
    df_qu_gold['score_vivabilite'],
    bins=[0, 33, 66, 100],
    labels=['Peu vivable', 'Vivable', 'Très vivable'],
    include_lowest=True
)
df_qu_gold['dimensions_incluses'] = 'proprete,espaces_verts'
df_qu_gold['dimensions_exclues']  = 'bruit,no2,criminalite'

df_qu_gold = df_qu_gold.sort_values('rang').reset_index(drop=True)

assert len(df_qu_gold) == 80,              f"❌ {len(df_qu_gold)} quartiers (attendu 80)"
assert df_qu_gold['rang'].nunique() == 80, "❌ Rangs non uniques (quartier)"

print(f"\nTop 5 vivabilité quartier :")
print(df_qu_gold[['code_quartier', 'nom_quartier', 'arrondissement',
                   'rang', 'score_vivabilite_100', 'categorie']].head(5).to_string(index=False))

exporter(
    df_qu_gold,
    table_name='score_vivabilite_quartier',
    pk_col='code_quartier',
    parquet_path=os.path.join(GOLD_DIR, 'score_vivabilite_quartier_gold.parquet'),
    engine=engine
)

print('\n=== GOLD vivabilité OK ===')
print('⚠️  Score quartier basé sur 2/5 dimensions (propreté + espaces verts)')
print('    Criminalité, bruit et NO2 non disponibles à la granularité quartier.')
