import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

# Lecture du CSV brut des arrêts/lignes
df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrets-lignes.csv',
                 sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# Lecture du CSV des polygones de quartiers (sous-arrondissements)
df_qu = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/quartiers.csv', sep=';')

# Renommage des colonnes brutes
df = df.rename(columns={
    'shortname'      : 'route_short_name',
    'mode'           : 'route_type',
    'nom_commune'    : 'commune',
    'operatorname'   : 'operateur',
    'route_long_name': 'ligne_nom',
    'code_insee'     : 'code_insee',
})
df = df.drop(columns=[c for c in ['bookingrules', 'pointgeo'] if c in df.columns])

# Conversion coordonnées
df['stop_lat'] = pd.to_numeric(df['stop_lat'], errors='coerce')
df['stop_lon'] = pd.to_numeric(df['stop_lon'], errors='coerce')

before = len(df)
df = df.dropna(subset=['stop_lat', 'stop_lon'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['stop_id', 'route_short_name'])
print(f"Doublons supprimés : {before - len(df)}")

df = df[df['stop_lat'].between(48.0, 49.4) & df['stop_lon'].between(1.4, 3.6)].copy()
print(f"Shape après filtrage IDF : {df.shape}")

MODE_MAP = {
    'Tramway'      : 'Tram',
    'Metro'        : 'Métro',
    'RailShuttle'  : 'Navette',
    'Bus'          : 'Bus',
    'LocalTrain'   : 'Train',
    'RapidTransit' : 'RER',
    'CableWay'     : 'Câble',
    'regionalRail' : 'Train Régional',
    'Funicular'    : 'Funiculaire',
}
df['mode_nom'] = df['route_type'].map(MODE_MAP).fillna('Autre')
print(f"Modes détectés : {df['mode_nom'].unique()}")

gdf_arrets = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['stop_lon'], df['stop_lat']),
    crs="EPSG:4326"
)

# Parsing de la géométrie des quartiers
def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str)) if pd.notna(geom_str) else None
    except Exception:
        return None

# Détection colonnes quartiers
geo_col_qu = next((c for c in df_qu.columns if 'geometry' in c.lower() and 'x y' not in c.lower()), None)
if not geo_col_qu:
    geo_col_qu = next((c for c in df_qu.columns if 'geom' in c.lower()), None)

df_qu['geometry'] = df_qu[geo_col_qu].apply(parse_geometry)
df_qu = df_qu.dropna(subset=['geometry'])
gdf_qu = gpd.GeoDataFrame(df_qu, geometry='geometry', crs="EPSG:4326")

# Colonnes à garder du CSV quartiers
cols_qu = ['C_QU', 'L_QU', 'C_AR', 'geometry']
cols_qu = [c for c in cols_qu if c in gdf_qu.columns]

# Jointure spatiale arrêts → quartier
resultat = gpd.sjoin(gdf_arrets, gdf_qu[cols_qu], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

# Renommage colonnes quartier
resultat = resultat.rename(columns={
    'C_QU': 'code_quartier',
    'L_QU': 'nom_quartier',
    'C_AR': 'arrondissement',
})

# Suppression des arrêts hors Paris (sans quartier)
df_final = resultat.dropna(subset=['code_quartier']).copy()
df_final['code_quartier'] = df_final['code_quartier'].astype(int)
df_final['arrondissement'] = df_final['arrondissement'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry'] if c in df_final.columns])

print(f"Arrêts Paris retenus : {len(df_final):,}")
print(f"Quartiers uniques : {df_final['code_quartier'].nunique()}")

cols_drop_final = ['code_insee']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'arrets_lignes_paris_silver.parquet')
df_final.to_parquet(output, index=False)
print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")