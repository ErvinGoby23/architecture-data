import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRUTE_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'brute'))

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

output_dir = os.path.join(BASE_DIR, 'nettoyage-indicateur4', date_str)
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'commissariats_paris_silver.parquet')

print(f"[{datetime.now().strftime('%H:%M:%S')}] Début du traitement Silver : Commissariats ({date_str})")

FILE = os.path.join(BRUTE_DIR, 'Score densité de services du quotidien', 'cartographie-des-emplacements-des-commissariats-a-paris-et-petite-couronne.csv')
df = pd.read_csv(FILE, sep=';', engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Lignes initiales : {len(df):,}")

df = df.rename(columns={
    'name': 'commissariat_nom',
    'description': 'type_commissariat'
})
df['commissariat_nom'] = df['commissariat_nom'].fillna('Non renseigné')

def parse_geometry(val):
    try:
        g = json.loads(val)
        lon, lat = g['coordinates']
        return pd.Series({'lon': lon, 'lat': lat})
    except Exception:
        return pd.Series({'lon': None, 'lat': None})

df[['lon', 'lat']] = df['geometry'].apply(parse_geometry)
df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
df['lon'] = pd.to_numeric(df['lon'], errors='coerce')

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"   Sans coordonnées supprimés : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['commissariat_nom', 'lat', 'lon'], keep='last')
print(f"   Doublons stricts supprimés : {before - len(df)}")

gdf_commissariats = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df['lon'], df['lat']), crs="EPSG:4326"
)

df_arr = pd.read_csv(os.path.join(BRUTE_DIR, 'indicateur-Score-accessibilité-mobilité', 'arrondissements.csv'), sep=';')
df_qu  = pd.read_csv(os.path.join(BRUTE_DIR, 'indicateur-Score-accessibilité-mobilité', 'quartiers.csv'), sep=';')

def parse_arr_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_arr_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_commissariats, gdf_arr[cols_arr], how='left', predicate='within')

if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

resultat = resultat.drop(columns=[c for c in ['index_right'] if c in resultat.columns])

def parse_qu_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None

geo_col_qu = next((c for c in df_qu.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None)
if not geo_col_qu:
    geo_col_qu = next((c for c in df_qu.columns if 'geom' in c.lower()), None)

df_qu['geometry'] = df_qu[geo_col_qu].apply(parse_qu_geometry)
df_qu = df_qu.dropna(subset=['geometry'])
gdf_qu = gpd.GeoDataFrame(df_qu, geometry='geometry', crs="EPSG:4326")

cols_qu = [c for c in ['C_QU', 'L_QU', 'geometry'] if c in gdf_qu.columns]

resultat = gpd.GeoDataFrame(resultat, geometry=gpd.points_from_xy(resultat['lon'], resultat['lat']), crs="EPSG:4326")
resultat = gpd.sjoin(resultat, gdf_qu[cols_qu], how='left', predicate='within')
resultat = resultat.rename(columns={'C_QU': 'code_quartier', 'L_QU': 'nom_quartier'})

df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal']   = df_final['code_postal'].astype(int)
df_final['code_quartier'] = pd.to_numeric(df_final['code_quartier'], errors='coerce').astype('Int64')

cols_drop_final = ['index_right', 'geometry', 'geo_point_2d', col_num, 'arrondissement', col_insee]
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])
df_final = df_final.drop(columns=[c for c in df_final.columns if c.startswith('index_right')])

print(f"   Lignes conservées (Paris intra-muros) : {len(df_final)}")
print(f"   Codes postaux générés : {sorted(df_final['code_postal'].unique())}")

df_final.to_parquet(output_file, index=False)
print(f"[{datetime.now().strftime('%H:%M:%S')}] Terminé. Fichier généré : {output_file}")