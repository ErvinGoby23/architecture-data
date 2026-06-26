"""
silver_proprete.py — Nettoyage Propreté urbaine Paris (DansMaRue)
Score de Vivabilité · Silver layer
Année de référence : 2025 (seule source disponible)
NB : aucun calcul de score ici — les poids et scores appartiennent au Gold.

RÈGLES DE FILTRAGE DES COORDONNÉES :
  Gardés  → signalements citoyens visibles sur la voie publique
  Exclus  → interventions internes (INTERVENANT contient 'Fonctionnelle')
             types purement techniques sans impact visuel (Eau, Eclairage)
"""

import pandas as pd
import geopandas as gpd
import json
import os
import sys
from shapely.geometry import shape
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilite')
FILE        = os.path.join(BRUTE_DIR, 'proprete.csv')

SILVER_BASE = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'indicateur3', 'nettoyage-indicateur3')

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
print(f"=== SILVER PROPRETE — Date : {date_str} ===")

ANNEE_REF = 2025

# Types exclus : infrastructure technique, sans impact visuel sur la voie publique
TYPES_EXCLUS = {'Éclairage / Électricité', 'Eau'}

# ==========================================================================
# 1. LECTURE en chunks + filtre 2025
# ==========================================================================
print("Lecture proprete.csv en chunks...")
chunks = []
for chunk in pd.read_csv(FILE, sep=';', engine='python', chunksize=100_000,
                          dtype=str, on_bad_lines='skip'):
    chunk.columns = chunk.columns.str.strip().str.replace('\ufeff', '', regex=False)
    chunks.append(chunk)

df = pd.concat(chunks, ignore_index=True)
print(f"Shape brute : {df.shape}")
print(f"Années disponibles : {sorted(df['ANNEE DECLARATION'].dropna().unique())}")

# Filtre sur l'année de référence (source multi-années)
before = len(df)
df = df[df['ANNEE DECLARATION'].astype(str).str.strip() == str(ANNEE_REF)].copy()
print(f"Filtre {ANNEE_REF} : {before - len(df):,} lignes autres années supprimées → {len(df):,} restantes")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
df['ARRONDISSEMENT']    = pd.to_numeric(df['ARRONDISSEMENT'],    errors='coerce').astype('Int64')
df['CODE POSTAL']       = pd.to_numeric(df['CODE POSTAL'],       errors='coerce').astype('Int64')
df['ANNEE DECLARATION'] = pd.to_numeric(df['ANNEE DECLARATION'], errors='coerce').astype('Int64')
df['MOIS DECLARATION']  = pd.to_numeric(df['MOIS DECLARATION'],  errors='coerce').astype('Int64')
df['DATE DECLARATION']  = pd.to_datetime(df['DATE DECLARATION'], errors='coerce')

df.loc[df['CODE POSTAL'] == 75248, 'CODE POSTAL']    = 75020
df.loc[df['CODE POSTAL'] == 75248, 'ARRONDISSEMENT'] = 20

before = len(df)
df = df[df['ARRONDISSEMENT'].between(1, 20)].dropna(subset=['ARRONDISSEMENT', 'DATE DECLARATION']).copy()
print(f"Hors Paris / sans date supprimés : {before - len(df)}")

# ==========================================================================
# 3. FILTRAGE SIGNALEMENTS
# Exclus : types techniques + interventions internes (patrouilles fonctionnelles)
# ==========================================================================
before = len(df)

# Exclusion par type (Eau, Eclairage)
mask_type = df['TYPE DECLARATION'].isin(TYPES_EXCLUS)

# Exclusion par intervenant : patrouilles et actions internes DPE
mask_intervenant = df['INTERVENANT'].astype(str).str.contains('Fonctionnelle', case=False, na=False)

# Types à impact visuel faible/nul sur l'espace public — exclus du score vivabilité
# Activités commerciales : conflits pro, pas de dégradation visible
# Arbres, végétaux, animaux : géré par espaces verts (autre indicateur)
# Dégradation du sol : infrastructure, pas visible au quotidien
TYPES_IMPACT_FAIBLE = {
    'Activités commerciales et professionnelles',
    'Arbres, végétaux et animaux',
    'Dégradation du sol',
    'Objets abandonnés',
    'Voirie et espace public',
}
mask_impact_faible = df['TYPE DECLARATION'].isin(TYPES_IMPACT_FAIBLE)

df = df[~mask_type & ~mask_intervenant & ~mask_impact_faible].copy()
print(f"Signalements exclus (types techniques + interventions internes) : {before - len(df):,}")
print(f"Types restants : {sorted(df['TYPE DECLARATION'].dropna().unique())}")

# ==========================================================================
# 4. COORDONNÉES — parse + filtre immédiat des vides/hors-Paris
# ==========================================================================
coords = df['geo_point_2d'].str.split(',', expand=True)
df['latitude']  = pd.to_numeric(coords[0], errors='coerce')
df['longitude'] = pd.to_numeric(coords[1], errors='coerce')

before = len(df)
df = df.dropna(subset=['latitude', 'longitude']).copy()
# Bbox Paris : lat 48.81–48.91 / lon 2.22–2.47
df = df[
    df['latitude'].between(48.81, 48.91) &
    df['longitude'].between(2.22, 2.47)
].copy()
print(f"Coords vides ou hors Paris supprimées : {before - len(df):,}")

# Doublons sur id_declaration
before = len(df)
df = df.drop_duplicates(subset=['ID DECLARATION']).copy()
print(f"Doublons id_declaration supprimés : {before - len(df):,}")

# Garder uniquement les colonnes brutes — pas de calcul de poids ici (Gold)
df = df[[c for c in [
    'ID DECLARATION', 'TYPE DECLARATION',
    'ARRONDISSEMENT', 'MOIS DECLARATION',
    'latitude', 'longitude',
] if c in df.columns]].rename(columns={
    'ID DECLARATION'   : 'id_declaration',
    'TYPE DECLARATION' : 'type_declaration',
    'ARRONDISSEMENT'   : 'arrondissement',
    'MOIS DECLARATION' : 'mois',
}).reset_index(drop=True)
print(f"Shape après nettoyage : {df.shape}")

# ==========================================================================
# 5. JOINTURE QUARTIER
# FIX : sjoin peut produire plusieurs lignes par point si les polygones
# se chevauchent. On déduplique sur l'index d'origine (keep='first')
# pour garantir 1 quartier max par signalement.
# ==========================================================================
def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None

df_qu = pd.read_csv(
    os.path.join(ROOT_DIR, 'architecture-data', 'brute',
                 'indicateur-Score-accessibilité-mobilité', 'quartiers.csv'), sep=';'
)
df_qu.columns = df_qu.columns.str.strip()
geo_col_qu = next((c for c in df_qu.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None)
if not geo_col_qu:
    geo_col_qu = next((c for c in df_qu.columns if 'geom' in c.lower()), None)

df_qu['geometry'] = df_qu[geo_col_qu].apply(parse_geometry)
gdf_qu = gpd.GeoDataFrame(df_qu.dropna(subset=['geometry']), geometry='geometry', crs="EPSG:4326")

# Toutes les lignes ont déjà des coords valides (filtrées section 4)
gdf_prop = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
    crs="EPSG:4326"
)

cols_qu_sel = [c for c in ['C_QU', 'L_QU', 'geometry'] if c in gdf_qu.columns]
res = gpd.sjoin(gdf_prop, gdf_qu[cols_qu_sel], how='left', predicate='within')
res = res.rename(columns={'C_QU': 'code_quartier', 'L_QU': 'nom_quartier'})

# Déduplique : 1 seule ligne par signalement
res = res[~res.index.duplicated(keep='first')]

avant = len(df)
df['code_quartier'] = None
df['nom_quartier']  = None
idx = res.index[res['code_quartier'].notna()]
df.loc[idx, 'code_quartier'] = res.loc[idx, 'code_quartier'].astype('Int64').values
df.loc[idx, 'nom_quartier']  = res.loc[idx, 'nom_quartier'].values
assert len(df) == avant, f"Duplication détectée après sjoin : {len(df)} vs {avant}"
print(f"Signalements avec code_quartier : {df['code_quartier'].notna().sum():,} / {len(df):,}")

# ==========================================================================
# 6. AGRÉGATION PAR ARRONDISSEMENT — comptage brut uniquement
# ==========================================================================
df_final_arr = df.groupby('arrondissement').agg(
    nb_signalements    = ('id_declaration',   'count'),
    nb_types_distincts = ('type_declaration', 'nunique'),
).reset_index()
df_final_arr['annee'] = ANNEE_REF
df_final_arr = df_final_arr.sort_values('arrondissement').reset_index(drop=True)
print(f"\nShape agrégée arrondissement : {df_final_arr.shape}")

# ==========================================================================
# 7. AGRÉGATION PAR QUARTIER — comptage brut uniquement
# ==========================================================================
df_qu_valid = df[df['code_quartier'].notna()].copy()
df_qu_valid['code_quartier'] = df_qu_valid['code_quartier'].astype(int)

df_final_qu = df_qu_valid.groupby('code_quartier').agg(
    nom_quartier       = ('nom_quartier',    'first'),
    arrondissement     = ('arrondissement',  'first'),
    nb_signalements    = ('id_declaration',  'count'),
    nb_types_distincts = ('type_declaration','nunique'),
).reset_index()
df_final_qu['annee'] = ANNEE_REF
df_final_qu = df_final_qu.sort_values('code_quartier').reset_index(drop=True)
print(f"Shape agrégée quartier : {df_final_qu.shape}")
print(f"Quartiers uniques : {df_final_qu['code_quartier'].nunique()}")

# ==========================================================================
# 8. EXPORT PARQUET versionné
#    - proprete_long_silver.parquet      : points bruts citoyens avec coords (MongoDB)
#    - proprete_silver.parquet           : agrégé arrondissement
#    - proprete_quartier_silver.parquet  : agrégé quartier
# ==========================================================================
output_dir = os.path.join(SILVER_BASE, date_str)
os.makedirs(output_dir, exist_ok=True)

out_long = os.path.join(output_dir, 'proprete_long_silver.parquet')
out      = os.path.join(output_dir, 'proprete_silver.parquet')
out_qu   = os.path.join(output_dir, 'proprete_quartier_silver.parquet')

df.to_parquet(out_long, index=False)
df_final_arr.to_parquet(out,   index=False)
df_final_qu.to_parquet(out_qu, index=False)

print(f"\n Parquet long            : {out_long}  ({len(df):,} signalements)")
print(f" Parquet arrondissement  : {out}  ({len(df_final_arr)} arrondissements)")
print(f" Parquet quartier        : {out_qu}  ({len(df_final_qu)} quartiers)")
print(f"Colonnes long            : {list(df.columns)}")
print(f"Colonnes arrondissement  : {list(df_final_arr.columns)}")
print(f"Colonnes quartier        : {list(df_final_qu.columns)}")