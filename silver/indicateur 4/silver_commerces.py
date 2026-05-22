"""
silver_commerces.py
Nettoyage + filtrage des commerces — Paris intra-muros uniquement (75)
"""

import pandas as pd
import os

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement des données...")
df = pd.read_csv(
    '../../brute/les-commerces-par-commune-ou-arrondissement-base-permanente-des-equipements.csv',
    sep=None, engine='python'
)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Shape brute : {df.shape}")
print(f"   Colonnes    : {list(df.columns)}")

# ── 2. Colonnes commerces ─────────────────────────────────────────────────
ADMIN_COLS = [
    'departement', 'departement_commune', 'libelle_de_commune',
    'arrondissement', 'canton_ville', 'zone_d_emploi',
    'unite_urbaine', 'population_2010', 'geo_point_2d', 'geo_shape'
]
COMMERCE_COLS = [c for c in df.columns if c not in ADMIN_COLS]
print(f"   Types de commerces détectés : {len(COMMERCE_COLS)}")

# ── 3. Filtrage Paris uniquement ──────────────────────────────────────────
print("\n🗺️  Filtrage Paris intra-muros (dept 75)...")
before = len(df)
df = df[df['departement'] == 75].copy()
print(f"   Lignes conservées : {len(df)} / {before} (autres départements exclus)")

# ── 4. Extraction lat / lon ────────────────────────────────────────────────
print("\n📍 Extraction des coordonnées...")
coords = df['geo_point_2d'].str.split(',', expand=True)
df['lat'] = pd.to_numeric(coords[0].str.strip(), errors='coerce')
df['lon'] = pd.to_numeric(coords[1].str.strip(), errors='coerce')

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"   Sans coords supprimés : {before - len(df)}")

# ── 5. Nettoyage du nom de commune ────────────────────────────────────────
print("\n🧹 Nettoyage des noms de communes...")
df['libelle_de_commune'] = (
    df['libelle_de_commune']
    .str.strip()
    .str.upper()
    .str.replace(r'\s+', ' ', regex=True)
)
print(f"   Communes : {sorted(df['libelle_de_commune'].unique())}")

# ── 6. Enrichissement arrondissement ──────────────────────────────────────
print("\n🏙️  Enrichissement arrondissement Paris...")

# La colonne 'arrondissement' du CSV est un code ex: 751, 752 ... 7520
# On recalcule le numéro proprement depuis departement_commune (75101 → 1)
df['arrondissement'] = df['departement_commune'].astype(str).str[-2:].astype(int)
print(f"   Arrondissements couverts : {sorted(df['arrondissement'].unique())}")

# ── 7. Calcul du total commerces ──────────────────────────────────────────
print("\n🛒 Calcul des totaux...")
df['total_commerces'] = df[COMMERCE_COLS].sum(axis=1)
print(f"   Total commerces Paris : {df['total_commerces'].sum():,}")
print(f"   Arrondissements sans commerce : {(df['total_commerces'] == 0).sum()}")

# ── 8. Validation bbox Paris intra-muros ──────────────────────────────────
print("\n✅ Validation géographique...")
before = len(df)
df = df[
    df['lat'].between(48.815, 48.905) &
    df['lon'].between(2.224, 2.470)
].copy()
print(f"   Hors bbox supprimés : {before - len(df)}")

# ── 9. Doublons ────────────────────────────────────────────────────────────
print("\n🔁 Suppression des doublons...")
before = len(df)
df = df.drop_duplicates(subset=['departement_commune'])
print(f"   Doublons supprimés : {before - len(df)}")

# ── 10. Sélection et ordre des colonnes finales ───────────────────────────
COLS_FINAL = [
    'libelle_de_commune',
    'arrondissement',
    'population_2010',
    'total_commerces',
    *COMMERCE_COLS,
    'lat',
    'lon',
    'geo_point_2d',
    'geo_shape',
]
df_final = df[COLS_FINAL].reset_index(drop=True)

# ── 11. Sauvegarde ────────────────────────────────────────────────────────
os.makedirs('nettoyage-commerces', exist_ok=True)
output = 'nettoyage-commerces/commerces_silver.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"\n✅ Fichier créé : {output}")
print(f"   Shape finale : {df_final.shape}")
print(f"   Colonnes     : {list(df_final.columns)}")

# ── 12. Vérification aléatoire ────────────────────────────────────────────
print("\n--- VÉRIFICATION ALÉATOIRE ---")
if len(df_final) == 0:
    print("⚠️  Aucune commune trouvée")
else:
    for _, row in df_final.sample(n=min(5, len(df_final)), random_state=42).iterrows():
        maps_url = f"https://www.google.com/maps?q={row['lat']},{row['lon']}"
        print(f"\nCommune      : {row['libelle_de_commune']}")
        print(f"Arrdt        : {int(row['arrondissement'])}e")
        print(f"Population   : {int(row['population_2010']):,}")
        print(f"Total comm.  : {int(row['total_commerces'])}")
        print(f"Lien         : {maps_url}")

print("\n--- FIN ---")
