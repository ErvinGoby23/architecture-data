import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

# Lecture du CSV brut des bornes d'appel taxi
df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/bornes-dappel-taxi.csv',
                 sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# Lecture du CSV des polygones de quartiers (sous-arrondissements)
df_qu = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/quartiers.csv', sep=';')

# Extraction coordonnées depuis geopoint
geo_col   = next((c for c in df.columns if 'geopoint' in c.lower()), None)
coords    = df[geo_col].str.split(',', expand=True)
df['lat'] = pd.to_numeric(coords[0], errors='coerce')
df['lon'] = pd.to_numeric(coords[1], errors='coerce')

cols_drop = ['no_appel', 'info', 'geo_shape', 'geopoint', 'geopoint_datagouv']
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df[df['lat'].between(41, 51) & df['lon'].between(-5, 10)]
print(f"Coords aberrantes : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['id'])
print(f"Doublons supprimés : {before - len(df)}")
print(f"Shape après nettoyage : {df.shape}")

gdf_bornes = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['lon'], df['lat']),
    crs="EPSG:4326"
)

# Parsing géométrie quartiers
def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None

geo_col_qu = next((c for c in df_qu.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None)
if not geo_col_qu:
    geo_col_qu = next((c for c in df_qu.columns if 'geom' in c.lower()), None)

df_qu['geometry'] = df_qu[geo_col_qu].apply(parse_geometry)
df_qu = df_qu.dropna(subset=['geometry'])
gdf_qu = gpd.GeoDataFrame(df_qu, geometry='geometry', crs="EPSG:4326")

cols_qu = ['C_QU', 'L_QU', 'C_AR', 'geometry']
cols_qu = [c for c in cols_qu if c in gdf_qu.columns]

# Jointure spatiale bornes → quartier
resultat = gpd.sjoin(gdf_bornes, gdf_qu[cols_qu], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

resultat = resultat.rename(columns={
    'C_QU': 'code_quartier',
    'L_QU': 'nom_quartier',
    'C_AR': 'arrondissement',
})

df_final = resultat.dropna(subset=['code_quartier']).copy()
df_final['code_quartier'] = df_final['code_quartier'].astype(int)
df_final['arrondissement'] = df_final['arrondissement'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry'] if c in df_final.columns])

print(f"Bornes Paris retenues : {len(df_final):,}")
print(f"Quartiers uniques : {df_final['code_quartier'].nunique()}")

df_final = df_final.rename(columns={
    'id'          : 'borne_id',
    'nom'         : 'borne_nom',
    'emplacements': 'nb_emplacements',
    'statut'      : 'statut',
})

cols_drop_final = ['code_insee']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'bornes_taxi_paris_silver.parquet')
df_final.to_parquet(output, index=False)
print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")