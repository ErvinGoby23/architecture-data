import pandas as pd
import geopandas as gpd
import json
import numpy as np
from shapely.geometry import shape
import os
import sys
from datetime import datetime

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
BRUTE_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'brute'))

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

output_dir  = os.path.join(BASE_DIR, 'nettoyage-indicateur4', date_str)
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'ecoles_elementaires_paris_silver.parquet')

print(f"[{datetime.now().strftime('%H:%M:%S')}] Début du traitement Silver : Écoles Élémentaires ({date_str})")

# ── helpers partagés (même pattern que silver_commissariats.py) ─────────────

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None

def load_gdf_arr(brute_dir):
    df = pd.read_csv(os.path.join(brute_dir, 'indicateur-Score-accessibilité-mobilité', 'arrondissements.csv'), sep=';')
    geo_col = next((c for c in df.columns if c.strip() == 'Geometry'), None) or \
              next((c for c in df.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
    col_num   = next((c for c in df.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
    col_insee = next((c for c in df.columns if 'insee' in c.lower()), None)
    df['geometry'] = df[geo_col].apply(parse_geometry)
    return gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326"), col_num, col_insee

def load_gdf_qu(brute_dir):
    df = pd.read_csv(os.path.join(brute_dir, 'indicateur-Score-accessibilité-mobilité', 'quartiers.csv'), sep=';')
    df.columns = df.columns.str.strip()
    geo_col = next((c for c in df.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None) or \
              next((c for c in df.columns if 'geom' in c.lower()), None)
    df['geometry'] = df[geo_col].apply(parse_geometry)
    df = df.dropna(subset=['geometry'])
    return gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")

def double_sjoin(gdf_points, gdf_arr, col_num, col_insee, gdf_qu):
    """Jointure spatiale arrondissement puis quartier — pattern ind2."""
    cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
    res = gpd.sjoin(gdf_points, gdf_arr[cols_arr], how='left', predicate='within')
    if col_num:
        res['arrondissement'] = res[col_num].fillna(0).astype(int)
        res['code_postal']    = (res['arrondissement'] + 75000).where(res['arrondissement'] > 0)
    res = res.drop(columns=[c for c in ['index_right', col_num, col_insee] if c in res.columns])

    cols_qu = [c for c in ['C_QU', 'L_QU', 'geometry'] if c in gdf_qu.columns]
    res = gpd.GeoDataFrame(res, geometry=gpd.points_from_xy(res['lon'], res['lat']), crs="EPSG:4326")
    res = gpd.sjoin(res, gdf_qu[cols_qu], how='left', predicate='within')
    res = res.rename(columns={'C_QU': 'code_quartier', 'L_QU': 'nom_quartier'})
    res = res.drop(columns=[c for c in res.columns if c.startswith('index_right')])
    return res

# ── chargement ──────────────────────────────────────────────────────────────

df = pd.read_csv(
    os.path.join(BRUTE_DIR, 'Score densité de services du quotidien',
                 'etablissements-scolaires-ecoles-elementaires.csv'),
    sep=None, engine='python'
)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Lignes initiales : {len(df):,}")

df = df.rename(columns={
    'Libellé établissement'                 : 'etablissement_nom',
    'Adresse'                               : 'adresse',
    'Type établissement'                    : 'type_etablissement',
    'Année scolaire'                        : 'annee_scolaire',
    'Code INSEE'                            : 'code_insee',
    "Type d'établissement - Année scolaire" : 'libelle_source',
})

# Extraction coords — vectorisé, zéro apply/lambda
coords     = df['geo_shape'].apply(json.loads).apply(lambda g: g['coordinates'])
df['lon']  = coords.str[0].astype(float)
df['lat']  = coords.str[1].astype(float)

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
df = df[df['lat'].between(48.0, 49.4) & df['lon'].between(1.4, 3.6)].copy()
print(f"   Hors IDF / Sans GPS supprimés : {before - len(df)}")

before = len(df)
df = df.sort_values('annee_scolaire', na_position='first')
df = df.drop_duplicates(subset=['etablissement_nom', 'lat', 'lon'], keep='last')
print(f"   Doublons supprimés : {before - len(df)}")

# ── jointures spatiales ─────────────────────────────────────────────────────

gdf_ecoles = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['lon'], df['lat']), crs="EPSG:4326")
gdf_arr, col_num, col_insee = load_gdf_arr(BRUTE_DIR)
gdf_qu = load_gdf_qu(BRUTE_DIR)

resultat = double_sjoin(gdf_ecoles, gdf_arr, col_num, col_insee, gdf_qu)

# ── finalisation ────────────────────────────────────────────────────────────

df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal']   = df_final['code_postal'].astype(int)
df_final['code_quartier'] = df_final['code_quartier'].astype('Int64')

cols_drop = [
    'geo_shape', 'geo_point_2d', 'Arrondissement', 'canton_ville',
    'geometry', col_num, 'arrondissement', 'code_insee',
    'arrondissement_insee', 'libelle_source', 'annee_scolaire'
]
df_final = df_final.drop(columns=[c for c in cols_drop if c in df_final.columns])

df_final.to_parquet(output_file, index=False)
print(f"[{datetime.now().strftime('%H:%M:%S')}] Terminé.")
print(f"   Lignes conservées (Paris intra-muros) : {len(df_final):,}")
print(f"   Fichier écrit : {output_file}")
print(f"   Codes postaux : {sorted(df_final['code_postal'].unique())}")