"""
silver_ecoles_elementaires.py
Nettoyage + filtrage des écoles élémentaires — Paris intra-muros uniquement (75)
"""

import pandas as pd
import os

# ── 1. Chargement ──────────────────────────────────────────────────────────
print("Chargement des données...")
df = pd.read_csv(
    '../../brute/etablissements-scolaires-ecoles-elementaires.csv',
    sep=None, engine='python'
)
df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
print(f"   Shape brute : {df.shape}")
print(f"   Colonnes    : {list(df.columns)}")

# ── 2. Renommage colonnes ──────────────────────────────────────────────────
df = df.rename(columns={
    "Type d'établissement - Année scolaire" : 'type_annee_scolaire',
    'Libellé établissement'                 : 'nom',
    'Adresse'                               : 'adresse',
    'Arrondissement'                        : 'arrondissement_label',
    'Code INSEE'                            : 'code_insee',
    'Type établissement'                    : 'type_etablissement',
    'Année scolaire'                        : 'annee_scolaire',
    'geo_shape'                             : 'geo_shape',
    'geo_point_2d'                          : 'geo_point_2d',
})

# ── 3. Filtrage Paris uniquement ──────────────────────────────────────────
print("\n🗺️  Filtrage Paris intra-muros (code INSEE 751xx)...")
before = len(df)
df = df[df['code_insee'].astype(str).str.startswith('751')].copy()
print(f"   Lignes conservées : {len(df)} / {before}")

# ── 4. Filtrage année scolaire la plus récente ────────────────────────────
print("\n📅 Filtrage sur l'année scolaire 2026-2027...")

before = len(df)
df = df[df['annee_scolaire'] == '2026-2027'].copy()

print(f"   Lignes conservées : {len(df)} / {before}")

# ── 5. Extraction lat / lon ────────────────────────────────────────────────
print("\n📍 Extraction des coordonnées...")
coords = df['geo_point_2d'].str.split(',', expand=True)
df['lat'] = pd.to_numeric(coords[0].str.strip(), errors='coerce')
df['lon'] = pd.to_numeric(coords[1].str.strip(), errors='coerce')

before = len(df)
df = df.dropna(subset=['lat', 'lon'])
print(f"   Sans coords supprimés : {before - len(df)}")

# ── 6. Nettoyage du nom ────────────────────────────────────────────────────
print("\n🧹 Nettoyage des noms...")
df['nom'] = (
    df['nom']
    .str.strip()
    .str.upper()
    .str.replace(r'\s+', ' ', regex=True)
)

# ── 7. Nettoyage du type établissement ───────────────────────────────────
print("\n🏷️  Nettoyage du type d'établissement...")
print(f"   Valeurs brutes : {df['type_etablissement'].unique().tolist()}")

df['type_etablissement'] = (
    df['type_etablissement']
    .str.strip()
    .str.title()
)
# Harmonisation variante "Elémentaire" / "Élémentaire"
df['type_etablissement'] = df['type_etablissement'].replace({
    'Elémentaire': 'Élémentaire',
})
print(f"   Valeurs après nettoyage : {df['type_etablissement'].unique().tolist()}")

# ── 8. Enrichissement arrondissement ──────────────────────────────────────
print("\n🏙️  Enrichissement arrondissement Paris...")
df['arrondissement'] = df['code_insee'].astype(str).str[-2:].astype(int)
print(f"   Arrondissements couverts : {sorted(df['arrondissement'].unique())}")

# ── 9. Validation bbox Paris intra-muros ──────────────────────────────────
print("\n✅ Validation géographique...")
before = len(df)
df = df[
    df['lat'].between(48.815, 48.905) &
    df['lon'].between(2.224, 2.470)
].copy()
print(f"   Hors bbox supprimés : {before - len(df)}")

# ── 10. Doublons ───────────────────────────────────────────────────────────
print("\n🔁 Suppression des doublons...")
before = len(df)
df = df.drop_duplicates(subset=['nom', 'code_insee'])
print(f"   Doublons (nom + code INSEE) supprimés : {before - len(df)}")

# ── 11. Sélection et ordre des colonnes finales ───────────────────────────
COLS_FINAL = [
    'nom',
    'type_etablissement',
    'adresse',
    'arrondissement',
    'code_insee',
    'lat',
    'lon',
    'geo_point_2d',
    'geo_shape',
]
df_final = df[COLS_FINAL].reset_index(drop=True)

# ── 12. Sauvegarde ────────────────────────────────────────────────────────
os.makedirs('nettoyage-ecoles', exist_ok=True)
output = 'nettoyage-ecoles/ecoles_elementaires_silver.csv'
df_final.to_csv(output, index=False, sep=';')
print(f"\n✅ Fichier créé : {output}")
print(f"   Shape finale : {df_final.shape}")
print(f"   Colonnes     : {list(df_final.columns)}")

# ── 13. Vérification aléatoire ────────────────────────────────────────────
print("\n--- VÉRIFICATION ALÉATOIRE ---")
if len(df_final) == 0:
    print("⚠️  Aucune école trouvée")
else:
    for _, row in df_final.sample(n=min(5, len(df_final)), random_state=42).iterrows():
        maps_url = f"https://www.google.com/maps?q={row['lat']},{row['lon']}"
        print(f"\nNom     : {row['nom']}")
        print(f"Type    : {row['type_etablissement']}")
        print(f"Adresse : {row['adresse']}")
        print(f"Arrdt   : {int(row['arrondissement'])}e")
        print(f"Lien    : {maps_url}")

print("\n--- FIN ---")
