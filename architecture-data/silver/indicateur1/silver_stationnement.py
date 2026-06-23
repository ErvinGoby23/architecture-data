import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import shape
import os
import glob

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BRUTE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '../../brute/indicateur-Score-accessibilité-mobilité'))

# Recherche dynamique de la dernière date disponible
dossiers_dates = [d for d in glob.glob(os.path.join(BRUTE_DIR, '*')) if os.path.isdir(d) and os.path.basename(d).replace('-', '').isdigit()]

if not dossiers_dates:
    raise FileNotFoundError(f"❌ Aucun dossier daté trouvé dans : {BRUTE_DIR}")

dernier_dossier = sorted(dossiers_dates)[-1]
date_str = os.path.basename(dernier_dossier)

path_stationnement = os.path.join(dernier_dossier, 'stationnement-voie-publique-emplacements.json')

print(f"📅 Dernière date de collecte trouvée : {date_str}")
print(f"📖 Lecture du fichier : {path_stationnement}")

with open(path_stationnement, encoding='utf-8') as f:
    data = json.load(f)

df = pd.DataFrame(data['records'])
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# Lecture du CSV des polygones de quartiers (sous-arrondissements)
path_quartiers = os.path.join(BRUTE_DIR, 'quartiers.csv')
df_qu = pd.read_csv(path_quartiers, sep=';')

# Extraction coordonnées
geo = df['geo_point_2d'].tolist()
df['latitude']  = pd.to_numeric([x.get('lat') if isinstance(x, dict) else None for x in geo], errors='coerce')
df['longitude'] = pd.to_numeric([x.get('lon') if isinstance(x, dict) else None for x in geo], errors='coerce')

cols_drop = [
    'geo_point_2d', 'geo_shape',
    'prefet', 'numilot', 'numiris',
    'plage_hor1_debut', 'plage_hor1_fin',
    'plage_hor2_debut', 'plage_hor2_fin',
    'plage_hor3_debut', 'plage_hor3_fin',
]
df = df.drop(columns=[c for c in cols_drop if c in df.columns])

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

gdf_stat = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
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

# Jointure spatiale stationnement → quartier
resultat = gpd.sjoin(gdf_stat, gdf_qu[cols_qu], how='left', predicate='within')
print(f"Shape après jointure : {resultat.shape}")

resultat = resultat.rename(columns={
    'C_QU': 'code_quartier',
    'L_QU': 'nom_quartier',
    'C_AR': 'arrondissement',
})

df_final = resultat.dropna(subset=['code_quartier']).copy()
df_final['code_quartier'] = df_final['code_quartier'].astype(int)
df_final['arrondissement'] = df_final['arrondissement'].astype(int)
df_final = pd.DataFrame(df_final.drop(columns=[c for c in ['index_right', 'geometry'] if c in df_final.columns]))

print(f"Emplacements Paris retenus : {len(df_final):,}")
print(f"Quartiers uniques : {df_final['code_quartier'].nunique()}")

cols_drop_final = ['arrondissement_source']
df_final = df_final.drop(columns=[c for c in cols_drop_final if c in df_final.columns])

# Validation spatiale
print("\n=== VALIDATION SPATIALE (échantillon 5 points) ===")
sample = df_final.groupby('code_quartier').first().reset_index()[
    ['code_quartier', 'nom_quartier', 'latitude', 'longitude', 'nom_voie', 'numero_voie']
].head(5)
for _, r in sample.iterrows():
    print(
        f"  Quartier {int(r['code_quartier'])} ({r['nom_quartier']}) | {r['numero_voie']} {r['nom_voie']}\n"
        f"  → http://maps.google.com/maps?q={r['latitude']},{r['longitude']}"
    )

output_dir = os.path.join('nettoyage-indicateur1', date_str)
os.makedirs(output_dir, exist_ok=True)
output = os.path.join(output_dir, 'stationnement_paris_silver.parquet')
df_final.to_parquet(output, index=False)
print(f"\n✓ Fichier Parquet créé : {output}")
print(f"Shape finale : {df_final.shape}")
print(f"Colonnes : {list(df_final.columns)}")