import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os

df = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/stationnement-voie-publique-emplacements.csv', sep=';', low_memory=False)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

df_arr = pd.read_csv('../../brute/indicateur-Score-accessibilité-mobilité/arrondissements.csv', sep=';')

cols_drop = [
    'Compétence préfecture', 'Numéro IRIS', 'Numéro ilot',
    'Plage horaire 1-Début', 'Plage horaire 1-Fin',
    'Plage horaire 2-Début', 'Plage horaire 2-Fin',
    'Plage horaire 3-Début', 'Plage horaire 3-Fin',
    'Complément numéro voie', 'Nouvel identifiant', 'Ancien identifiant',
    'Numéro mobilier', 'Type mobilier', 'Numéro séquentiel Tronçon voie',
    '1er numéro tronçon voie', 'Dernier numéro tronçon voie',
]
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

before = len(df)
df = df[df['Arrondissement'].between(1, 20)]
print(f"Arrond. aberrants supprimés : {before - len(df)}")

before = len(df)
df = df.drop_duplicates()
print(f"Doublons supprimés : {before - len(df)}")
print(f"Shape après nettoyage : {df.shape}")

df = df.rename(columns={
    'Régime prioritaire'        : 'regime_prioritaire',
    'Régime particulier'        : 'regime_particulier',
    'Type de stationnement'     : 'type_stationnement',
    'Arrondissement'            : 'arrondissement_source',
    'Nombre places calculées'   : 'nb_places_calcules',
    'Nombre places réelles'     : 'nb_places_reelles',
    'Zones Résidentielles'      : 'zone_residentielle',
    'Localisation stationnement': 'localisation',
    'Numéro voie'               : 'numero_voie',
    'Type voie'                 : 'type_voie',
    'Nom voie'                  : 'nom_voie',
    'Localisation numéro'       : 'localisation_numero',
    'Parité'                    : 'parite',
    'Longueur'                  : 'longueur',
    'Largeur'                   : 'largeur',
    'Surface calculée'          : 'surface_calculee',
    'Signalisation horizontale' : 'signalisation_h',
    'Signalisation verticale'   : 'signalisation_v',
    'Conformité signalisation'  : 'conformite_signal',
    'Code voie Ville de Paris'  : 'code_voie',
    'Zone ASP'                  : 'zone_asp',
    'Numéro Section Territoriale de Voirie': 'section_voirie',
    'Dernière modification'     : 'date_modif',
    'Date du relevé'            : 'date_releve',
})

df['date_modif']  = pd.to_datetime(df.get('date_modif'),  errors='coerce')
df['date_releve'] = pd.to_datetime(df.get('date_releve'), errors='coerce')

regime_map = {
    'GRATUIT'        : 'gratuit',
    'PAYANT MIXTE'   : 'payant',
    'PAYANT ROTATIF' : 'payant',
    '2 ROUES'        : '2roues',
    'ELECTRIQUE'     : 'electrique',
    'GIG/GIC'        : 'pmr',
}
df['regime_category'] = df['regime_prioritaire'].map(regime_map)
print(f"\nDistribution régimes :")
print(df['regime_category'].value_counts(dropna=False))

def parse_geometry(geom_str):
    try:
        return shape(json.loads(geom_str))
    except Exception:
        return None

def to_code_postal(arr):
    return 75000 + arr if arr > 0 else None

df['geometry'] = df['geo_shape'].apply(parse_geometry)
before = len(df)
df = df.dropna(subset=['geometry'])
print(f"Géométries invalides supprimées : {before - len(df)}")

gdf_stat = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
gdf_stat = gdf_stat.drop(columns=['geo_shape', 'geo_point_2d'], errors='ignore')

geo_col_arr = next((c for c in df_arr.columns if c.strip() == 'Geometry'), None)
if not geo_col_arr:
    geo_col_arr = next((c for c in df_arr.columns if 'geom' in c.lower() and 'x y' not in c.lower()), None)

col_num   = next((c for c in df_arr.columns if 'numéro' in c.lower() and 'insee' not in c.lower() and 'séquentiel' not in c.lower()), None)
col_insee = next((c for c in df_arr.columns if 'insee' in c.lower()), None)

df_arr['geometry'] = df_arr[geo_col_arr].apply(parse_geometry)
gdf_arr = gpd.GeoDataFrame(df_arr, geometry='geometry', crs="EPSG:4326")

cols_arr = [c for c in [col_num, col_insee, 'geometry'] if c]
resultat = gpd.sjoin(gdf_stat, gdf_arr[cols_arr], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

if col_num:
    resultat['arrondissement'] = resultat[col_num].fillna(0).astype(int)
    resultat['code_postal']    = resultat['arrondissement'].apply(to_code_postal)

if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)
df_final = df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns])

print(f"Emplacements Paris retenus : {len(df_final):,}")

cols_drop_final = ['code_insee', 'arrondissement_insee', 'arrondissement', 'arrondissement_source', 'code_insee_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

os.makedirs('nettoyage-indicateur1', exist_ok=True)
output = 'nettoyage-indicateur1/stationnement_final_paris.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"Fichier créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")