import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import glob

# Trouver le dossier actuel du script pour sécuriser les chemins
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BRUTE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '../../brute/indicateur-Score-accessibilité-mobilité'))


# RECHERCHE DYNAMIQUE DE LA DERNIÈRE DATE DISPONIBLE (Evite les crashs)

# On liste tous les sous-dossiers qui ont un format de date (AAAA-MM-JJ)
dossiers_dates = [d for d in glob.glob(os.path.join(BRUTE_DIR, '*')) if os.path.isdir(d) and os.path.basename(d).replace('-', '').isdigit()]

if not dossiers_dates:
    raise FileNotFoundError(f"❌ Aucun dossier daté trouvé dans : {BRUTE_DIR}")

# Tri alphabétique/chronologique pour choper le snapshot le plus récent
dernier_dossier = sorted(dossiers_dates)[-1]
date_str = os.path.basename(dernier_dossier)

path_stationnement = os.path.join(dernier_dossier, 'stationnement-voie-publique-emplacements.json')

print(f"📅 Dernière date de collecte trouvée : {date_str}")
print(f"📖 Lecture du fichier : {path_stationnement}")

#  Lecture JSON brute dynamique 
with open(path_stationnement, encoding='utf-8') as f:
    data = json.load(f)

df = pd.DataFrame(data['records'])
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# Le CSV des arrondissements reste à sa place fixe à la racine du dossier brute associé
path_arrondissements = os.path.join(BRUTE_DIR, 'arrondissements.csv')
df_arr = pd.read_csv(path_arrondissements, sep=';')

#  Extraction coords vectorisée (list comprehension > apply) 
geo = df['geo_point_2d'].tolist()
df['latitude']  = pd.to_numeric([x.get('lat') if isinstance(x, dict) else None for x in geo], errors='coerce')
df['longitude'] = pd.to_numeric([x.get('lon') if isinstance(x, dict) else None for x in geo], errors='coerce')

#  Suppression colonnes inutiles (EDA) 
cols_drop = [
    'geo_point_2d', 'geo_shape',
    'prefet', 'numilot', 'numiris',
    'plage_hor1_debut', 'plage_hor1_fin',
    'plage_hor2_debut', 'plage_hor2_fin',
    'plage_hor3_debut', 'plage_hor3_fin',
]
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

#  Renommage
df = df.rename(columns={
    'arrond'  : 'arrondissement_source',
    'typsta'  : 'type_stationnement',
    'regpar'  : 'regime_parking',
    'regpri'  : 'regime_priorite',
    'locsta'  : 'localisation',
    'placal'  : 'places_calculees',
    'plarel'  : 'places_relevees',
    'nomvoie' : 'nom_voie',
    'typevoie': 'type_voie',
    'numvoie' : 'numero_voie',
    'stv'     : 'secteur_voirie',
    'zoneasp' : 'zone_asp',
    'zoneres' : 'zone_residence',
})

#  Nettoyage vectorisé 
before = len(df)
df = df.dropna(subset=['latitude', 'longitude'])
print(f"Sans coords supprimés : {before - len(df)}")

before = len(df)
df = df[df['latitude'].between(48.7, 49.0) & df['longitude'].between(2.2, 2.5)].copy()
print(f"Hors Paris supprimés : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['id'])
print(f"Doublons supprimés : {before - len(df)}")
print(f"Shape après nettoyage : {df.shape}")

#  Géométrie vectorisée (points_from_xy = 10x plus rapide que apply)
gdf_stat = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
    crs="EPSG:4326"
)

#  Arrondissements -
def parse_geometry(geom_str):
    return shape(json.loads(geom_str)) if pd.notna(geom_str) else None

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
    resultat['code_postal']    = (resultat['arrondissement'] + 75000).where(resultat['arrondissement'] > 0)

if col_insee:
    resultat = resultat.rename(columns={col_insee: 'arrondissement_insee'})

df_final = resultat.dropna(subset=['code_postal']).copy()
df_final['code_postal'] = df_final['code_postal'].astype(int)

# On garde le format DataFrame standard après sjoin en retirant la colonne geometry
df_final = pd.DataFrame(df_final.drop(columns=[c for c in ['index_right', 'geometry', col_num] if c in df_final.columns]))

print(f"Emplacements Paris retenues : {len(df_final):,}")
print(f"Code postaux uniques : {sorted(df_final['code_postal'].unique())}")

cols_drop_final = ['arrondissement_insee', 'arrondissement', 'arrondissement_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

#  Validation spatiale (URL Maps valide) 
print("\n=== VALIDATION SPATIALE (échantillon 5 points) ===")
sample = df_final.groupby('code_postal').first().reset_index()[
    ['code_postal', 'latitude', 'longitude', 'nom_voie', 'numero_voie']
].head(5)
for _, r in sample.iterrows():
    print(
        f"  CP {int(r['code_postal'])} | {r['numero_voie']} {r['nom_voie']}\n"
        f"  → http://maps.google.com/maps?q={r['latitude']},{r['longitude']}"
    )

#  Export Parquet sécurisé dans le répertoire du script
output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'stationnement_paris_silver.parquet')
df_final.to_parquet(output, index=False)
print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")