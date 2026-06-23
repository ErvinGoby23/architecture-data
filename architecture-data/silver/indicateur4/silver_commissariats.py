import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
from datetime import datetime

# ==========================================
# 0. Configuration & Paramètres
# ==========================================
output_dir = 'nettoyage-indicateur-commissariats'
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'commissariats_paris_silver.parquet')

print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Début du traitement Silver : Commissariats (Sans Date)")

# ==========================================
# 1. Chargement & Préparation (Source Brute)
# ==========================================
FILE = '../../brute/Score densité de services du quotidien/cartographie-des-emplacements-des-commissariats-a-paris-et-petite-couronne.csv'
df = pd.read_csv(FILE, sep=';', engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   ↳ Lignes initiales : {len(df):,}")

# Renommage et gestion des valeurs nulles
df = df.rename(columns={
    'name': 'commissariat_nom',
    'description': 'type_commissariat'
})

# Certains points n'ont pas de nom, on les identifie pour éviter les erreurs
df['commissariat_nom'] = df['commissariat_nom'].fillna('Non renseigné')

# ==========================================
# 2. Traitement Géographique
# ==========================================
def parse_geometry(val):
    try:
        g = json.loads(val)
        lon, lat = g['coordinates']
        return pd.Series({'lon': lon, 'lat': lat})
    except Exception:
        return pd.Series({'lon': None, 'lat': None})

# Appliquer l'extraction
df[['lon', 'lat']] = df['geometry'].apply(parse_geometry)
df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
df['lon'] = pd.to_numeric(df['lon'], errors='coerce')

# Nettoyage des coordonnées vides
before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"   ↳ Sans coordonnées supprimés : {before - len(df)}")

# ==========================================
# 3. 🔥 DÉDOUBLONNAGE (Clé Composite Sans Date) 🔥
# ==========================================
# On dédoublonne sur : Entité (Nom) + Spatial (GPS)
before = len(df)
df = df.drop_duplicates(subset=['commissariat_nom', 'lat', 'lon'], keep='last')
print(f"   ↳ Doublons stricts supprimés : {before - len(df)}")

# ==========================================
# 4. Jointure Spatiale (Codes Postaux)
# ==========================================
# Commissariats
gdf_commissariats = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df['lon'], df['lat']), crs="EPSG:4326"
)

# Arrondissements
df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

def parse_arr_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_arr_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

# Jointure spatiale
cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_commissariats, gdf_arr[cols_arr], how='left', predicate='within')

# Construction du code postal
if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

# ==========================================
# 5. Filtrage Final et Nettoyage
# ==========================================
# On supprime tout ce qui n'a pas matché d'arrondissement (Petite Couronne)
df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)

# Nettoyage des colonnes techniques
cols_drop_final = ['index_right', 'geometry', 'geo_point_2d', col_num, 'arrondissement', col_insee]
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

print(f"   ↳ Lignes conservées (Paris intra-muros) : {len(df_final)}")
print(f"   ↳ Codes postaux générés : {sorted(df_final['code_postal'].unique())}")

# ==========================================
# 6. Exportation Parquet
# ==========================================
# Plus de partitionnement par date, on écrase l'ancien fichier
df_final.to_parquet(output_file, index=False)

print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Terminé avec succès. Fichier généré : {output_file}")