import pandas as pd
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRUTE_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'brute'))

date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

output_dir = os.path.join(BASE_DIR, 'nettoyage-indicateur4', date_str)
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'commerces_paris_silver.parquet')

print(f"[{datetime.now().strftime('%H:%M:%S')}] Début du traitement Silver : Commerces ({date_str})")

FILE = os.path.join(BRUTE_DIR, 'Score densité de services du quotidien', 'les-commerces-par-commune-ou-arrondissement-base-permanente-des-equipements.csv')
df = pd.read_csv(FILE, sep=';', engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Lignes initiales (Toute l'IDF) : {len(df):,}")

df = df.rename(columns={
    'departement_commune': 'code_insee',
    'libelle_de_commune': 'commune_nom'
})

df['code_insee'] = df['code_insee'].astype(str)
df = df[df['code_insee'].str.startswith('751')]
df = df[df['code_insee'].between('75101', '75120')]
print(f"   Lignes conservées (Paris intra-muros) : {len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['code_insee'], keep='last')
if before - len(df) > 0:
    print(f"   Doublons de communes supprimés : {before - len(df)}")

cols_drop_final = ['geo_point_2d', 'geo_shape', 'departement', 'canton_ville', 'zone_d_emploi', 'unite_urbaine']
df_final = df.drop(columns=[c for c in cols_drop_final if c in df.columns])

df_final.to_parquet(output_file, index=False)
print(f"[{datetime.now().strftime('%H:%M:%S')}] Terminé. Fichier généré : {output_file}")
print(f"   Codes INSEE présents : {sorted(df_final['code_insee'].unique())}")