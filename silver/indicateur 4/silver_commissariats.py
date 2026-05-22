"""
silver_commissariats.py
Nettoyage + filtrage des commissariats — Paris intra-muros uniquement (75)
"""

import pandas as pd
import os

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("📥 Chargement des données...")
df = pd.read_csv(
    '../../brute/commissariats_avec_code_postal.csv',
    sep=None, engine='python'
)
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"   Shape brute : {df.shape}")

# ── 2. Renommage colonnes ──────────────────────────────────────────────────
df = df.rename(columns={
    'name'        : 'nom',
    'geometry'    : 'geo_shape',
    'geo_point_2d': 'geo_point_2d',
    'code_postal' : 'code_postal',
})
df = df.drop(columns=['description'], errors='ignore')

# ── 3. Filtrage Paris uniquement ──────────────────────────────────────────
print("\n🗺️  Filtrage Paris intra-muros (75xxx)...")
before = len(df)
df = df[df['code_postal'].astype(str).str.startswith('75')].copy()
print(f"   Lignes conservées : {len(df)} / {before} (Petite Couronne exclue)")

# ── 4. Extraction lat / lon ────────────────────────────────────────────────
print("\n📍 Extraction des coordonnées...")
coords = df['geo_point_2d'].str.split(',', expand=True)
df['lat'] = pd.to_numeric(coords[0].str.strip(), errors='coerce')
df['lon'] = pd.to_numeric(coords[1].str.strip(), errors='coerce')

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"   Sans coords supprimés : {before - len(df)}")

# ── 5. Nettoyage du nom ────────────────────────────────────────────────────
print("\n🧹 Nettoyage des noms...")
mask_no_name = df['nom'].isna()
print(f"   Lignes sans nom avant nettoyage : {mask_no_name.sum()}")

df['nom'] = (
    df['nom']
    .str.strip()
    .str.upper()
    .str.replace(r'\s+', ' ', regex=True)
)

# Fallback : étiquette générique localisée
df.loc[df['nom'].isna(), 'nom'] = (
    'COMMISSARIAT_' +
    df.loc[df['nom'].isna(), 'lat'].round(4).astype(str) + '_' +
    df.loc[df['nom'].isna(), 'lon'].round(4).astype(str)
)
print(f"   Noms reconstruits (fallback) : {mask_no_name.sum()}")

# ── 6. Enrichissement arrondissement ──────────────────────────────────────
print("\n🏙️  Enrichissement arrondissement Paris...")
df['arrondissement'] = df['code_postal'].apply(
    lambda cp: int(str(cp)[-2:]) if str(cp) != '75000' else None
)
print(f"   Arrondissements couverts : {sorted(df['arrondissement'].dropna().astype(int).unique())}")

# ── 7. Validation bbox Paris intra-muros ──────────────────────────────────
print("\n✅ Validation géographique...")
before = len(df)
df = df[
    df['lat'].between(48.815, 48.905) &
    df['lon'].between(2.224, 2.470)
].copy()
print(f"   Hors bbox supprimés : {before - len(df)}")

# ── 8. Doublons ────────────────────────────────────────────────────────────
print("\n🔁 Suppression des doublons...")
before = len(df)
df = df.drop_duplicates(subset=['lat', 'lon'])
print(f"   Doublons (lat+lon) supprimés : {before - len(df)}")

# ── 9. Sélection et ordre des colonnes finales ────────────────────────────
COLS_FINAL = [
    'nom',
    'code_postal',
    'arrondissement',
    'lat',
    'lon',
    'geo_point_2d',
    'geo_shape',
]
df_final = df[COLS_FINAL].reset_index(drop=True)

# ── 10. Sauvegarde ────────────────────────────────────────────────────────
os.makedirs('nettoyage-commissariats', exist_ok=True)
output = 'nettoyage-commissariats/commissariats_silver.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"\n✅ Fichier créé : {output}")
print(f"   Shape finale : {df_final.shape}")
print(f"   Colonnes     : {list(df_final.columns)}")

# ── 11. Vérification aléatoire ────────────────────────────────────────────
print("\n--- VÉRIFICATION ALÉATOIRE ---")
if len(df_final) == 0:
    print("⚠️  Aucun commissariat trouvé")
else:
    for _, row in df_final.sample(n=min(5, len(df_final)), random_state=42).iterrows():
        maps_url = f"https://www.google.com/maps?q={row['lat']},{row['lon']}"
        print(f"\nNom     : {row['nom']}")
        print(f"CP      : {row['code_postal']}  |  Arrdt : {int(row['arrondissement'])}e")
        print(f"Lien    : {maps_url}")

print("\n--- FIN ---")
