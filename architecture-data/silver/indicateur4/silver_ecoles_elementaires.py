import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import sys
from datetime import datetime

# ==========================================
# 0. Configuration & Paramètres
# ==========================================
date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'ecoles_elementaires_paris_silver.parquet')

# ==========================================
# 1. Chargement & Préparation (Source Brute)
# ==========================================
print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Début du traitement Silver : Écoles Élémentaires")

df = pd.read_csv('../../brute/Score densité de services du quotidien/etablissements-scolaires-ecoles-elementaires.csv',
                 sep=None, engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   ↳ Lignes initiales : {len(df):,}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

# Renommage (standard snake_case)
df = df.rename(columns={
    'Libellé établissement'                 : 'etablissement_nom',
    'Adresse'                               : 'adresse',
    'Type établissement'                    : 'type_etablissement',
    'Année scolaire'                        : 'annee_scolaire',
    'Code INSEE'                            : 'code_insee',
    "Type d'établissement - Année scolaire" : 'libelle_source',
})

# ==========================================
# 2. Traitement Géographique
# ==========================================
# Extraction des coordonnées (GeoJSON)
def parse_point(val):
    try:
        g = json.loads(val)
        return pd.Series({'lon': g['coordinates'][0], 'lat': g['coordinates'][1]})
    except Exception:
        return pd.Series({'lon': None, 'lat': None})

df[['lon', 'lat']] = df['geo_shape'].apply(parse_point)
df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
df['lon'] = pd.to_numeric(df['lon'], errors='coerce')

# Filtrage strict : Île-de-France (pour la performance) et Coordonnées Valides
before = len(df)
df = df.dropna(subset=['lat', 'lon'])
df = df[df['lat'].between(48.0, 49.4) & df['lon'].between(1.4, 3.6)].copy()
print(f"   ↳ Hors IDF / Sans GPS supprimés : {before - len(df)}")

# ==========================================
# 3. 🔥 DÉDOUBLONNAGE (Clé Composite SANS la date) 🔥
# ==========================================
# On trie d'abord par année scolaire pour s'assurer que la fonction `keep='last'` 
# conserve bien la version la plus récente de chaque école.
before = len(df)
df = df.sort_values('annee_scolaire', na_position='first')

# La clé ne contient plus 'annee_scolaire'
df = df.drop_duplicates(subset=['etablissement_nom', 'lat', 'lon'], keep='last')
print(f"   ↳ Doublons stricts supprimés (Historique écrasé) : {before - len(df)}")

# ==========================================
# 4. Jointure Spatiale (Codes Postaux)
# ==========================================
# Écoles
gdf_ecoles = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['lon'], df['lat']), crs="EPSG:4326")

# Arrondissements
def parse_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)
col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

# Jointure
cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_ecoles, gdf_arr[cols_arr], how='left', predicate='within')

# Calcul Codes Postaux
if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

# ==========================================
# 5. Filtrage Final et Nettoyage
# ==========================================
# On supprime tout ce qui n'est pas tombé dans un arrondissement (Petite Couronne)
df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)

# Nettoyage des colonnes inutiles pour la couche Silver
# Ajout de 'annee_scolaire' car l'historique n'est plus conservé
cols_drop_final = [
    'geo_shape', 'geo_point_2d', 'Arrondissement', 'canton_ville',
    'index_right', 'geometry', col_num, 'arrondissement', 'code_insee', 
    'arrondissement_insee', 'libelle_source', 'annee_scolaire'
]
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

# ==========================================
# 6. Exportation Parquet
# ==========================================
df_final.to_parquet(output_file, index=False)

print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Terminé avec succès.")
print(f"   ↳ Lignes conservées (Paris intra-muros) : {len(df_final):,}")
print(f"   ↳ Fichier écrit : {output_file}")
print(f"   ↳ Codes postaux : {sorted(df_final['code_postal'].unique())}")