import pandas as pd
import os
from datetime import datetime

# Ancrage des chemins sur l'emplacement du script (indépendant du répertoire courant)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRUTE_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'brute'))

# ==========================================
# 0. Configuration & Paramètres
# ==========================================
output_dir = os.path.join(BASE_DIR, 'nettoyage-indicateur-commerces')
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'commerces_paris_silver.parquet')

print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Début du traitement Silver : Commerces (Sans Date)")

# ==========================================
# 1. Chargement & Préparation (Source Brute)
# ==========================================
FILE = os.path.join(BRUTE_DIR, 'Score densité de services du quotidien', 'les-commerces-par-commune-ou-arrondissement-base-permanente-des-equipements.csv')
df = pd.read_csv(FILE, sep=';', engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   ↳ Lignes initiales (Toute l'IDF) : {len(df):,}")

# Renommage optionnel si tu souhaites clarifier certaines colonnes
# (Le fichier a déjà de bons noms en snake_case, mais on peut ajuster)
df = df.rename(columns={
    'departement_commune': 'code_insee',
    'libelle_de_commune': 'commune_nom'
})

# ==========================================
# 2. Filtrage Strict : Paris Uniquement
# ==========================================
# Les codes INSEE des arrondissements de Paris vont de 75101 à 75120
# Pour des données sous format numérique ou texte, on s'assure du bon type
df['code_insee'] = df['code_insee'].astype(str)
df = df[df['code_insee'].str.startswith('751')]

# On peut aussi s'assurer qu'il s'agit bien des 20 arrondissements (et exclure 75056 qui est "Paris" global)
df = df[df['code_insee'].between('75101', '75120')]

print(f"   ↳ Lignes conservées (Paris intra-muros) : {len(df)}")

# ==========================================
# 3. 🔥 DÉDOUBLONNAGE (Clé Unique : Code INSEE) 🔥
# ==========================================
before = len(df)
df = df.drop_duplicates(subset=['code_insee'], keep='last')
if before - len(df) > 0:
    print(f"   ↳ Doublons de communes supprimés : {before - len(df)}")
else:
    print("   ↳ Aucun doublon détecté sur le code INSEE.")

# ==========================================
# 4. Nettoyage Final
# ==========================================
# On supprime les colonnes inutiles pour l'indicateur (géométrie brute, etc.)
cols_drop_final = ['geo_point_2d', 'geo_shape', 'departement', 'canton_ville', 'zone_d_emploi', 'unite_urbaine']
df_final = df.drop(columns=[c for c in cols_drop_final if c in df.columns])

# ==========================================
# 5. Exportation Parquet
# ==========================================
# On écrase l'ancien fichier à chaque exécution (pas de partitionnement par date)
df_final.to_parquet(output_file, index=False)

print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Terminé avec succès. Fichier généré : {output_file}")
print(f"   ↳ Codes INSEE présents : {sorted(df_final['code_insee'].unique())}")