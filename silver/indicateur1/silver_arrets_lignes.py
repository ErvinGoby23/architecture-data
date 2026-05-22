import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape, Point
import os

df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrets-lignes.csv', sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

df = df.rename(columns={
    'shortname'      : 'route_short_name',
    'mode'           : 'route_type',
    'nom_commune'    : 'commune',
    'operatorname'   : 'operateur',
    'route_long_name': 'ligne_nom',
    'code_insee'     : 'code_insee',
})

df = df.drop(columns=[c for c in ['bookingrules', 'pointgeo'] if c in df.columns])

df['stop_lat'] = pd.to_numeric(df['stop_lat'], errors='coerce')
df['stop_lon'] = pd.to_numeric(df['stop_lon'], errors='coerce')

before = len(df)
df = df.dropna(subset=['stop_lat', 'stop_lon'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['stop_id', 'route_short_name'])
print(f"Doublons supprimés : {before - len(df)}")

df = df[
    df['stop_lat'].between(48.0, 49.4) &
    df['stop_lon'].between(1.4, 3.6)
].copy()
print(f"Shape après filtrage IDF : {df.shape}")

def make_point(row):
    return Point(row['stop_lon'], row['stop_lat'])

df['geometry'] = df.apply(make_point, axis=1)
gdf_arrets = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str))
    except Exception:
        return None

def to_code_postal(arr):
    return 75000 + arr if arr > 0 else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_arrets, gdf_arr[cols_arr], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = resultat['arrondissement'].apply(to_code_postal)

if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns])

print(f"Arrêts Paris retenus : {len(df_final):,}")
print(f"Code postaux uniques : {sorted(df_final['code_postal'].unique())}")

cols_drop_final = ['code_insee', 'arrondissement_insee', 'arrondissement', 'arrondissement_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

os.makedirs('nettoyage-indicateur1', exist_ok=True)
output = 'nettoyage-indicateur1/arrets_lignes_final_paris.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"Fichier créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")