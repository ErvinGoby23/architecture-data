"""
silver_NO2.py — Nettoyage NO₂ tronçons Périphérique parisien
Score de Vivabilité · Silver layer
"""

import pandas as pd
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
FILE        = os.path.join(BRUTE_DIR, 'NO2.csv')

SEUIL_OMS_ANNUEL  = 40.0   # µg/m³ moyenne annuelle
SEUIL_OMS_HORAIRE = 200.0  # µg/m³ seuil horaire à ne pas dépasser plus de 18x/an

# ==========================================================================
# 1. LECTURE
# ==========================================================================
df = pd.read_csv(FILE, sep=',', engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
df['time'] = pd.to_datetime(df['time'], errors='coerce')
print(f"Shape brute : {df.shape}")
print(f"Période : {df['time'].min()} → {df['time'].max()}")

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
troncons = [c for c in df.columns if c != 'time']

before = len(df)
df = df.dropna(subset=['time'])
print(f"Lignes sans timestamp supprimées : {before - len(df)}")

before = len(df)
df = df.drop_duplicates(subset=['time'])
print(f"Doublons supprimés : {before - len(df)}")

df = df.sort_values('time').reset_index(drop=True)

# Interpolation linéaire des NaN (~1.1%)
for col in troncons:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df[troncons] = df[troncons].interpolate(method='linear', limit=3)

nan_restants = df[troncons].isnull().sum().sum()
print(f"NaN restants après interpolation : {nan_restants}")

# ==========================================================================
# 3. AGRÉGATIONS TEMPORELLES
# ==========================================================================
df = df.set_index('time')

# Journalière
df_jour = df[troncons].resample('D').mean().round(2)
df_jour.columns = [f'{c}_no2_moy_jour' for c in df_jour.columns]

# Mensuelle
df_mois = df[troncons].resample('ME').mean().round(2)
df_mois.columns = [f'{c}_no2_moy_mois' for c in df_mois.columns]

# Horaire (profil moyen par heure)
df_heure = df.copy()
df_heure['heure'] = df_heure.index.hour
df_profil = df_heure.groupby('heure')[troncons].mean().round(2).reset_index()

# Annuelle + dépassements seuil OMS
df_annee = df[troncons].resample('YE').agg(
    ['mean', 'max', 'std']
).round(2)
df_annee.columns = [f'{col}_{stat}' for col, stat in df_annee.columns]

# Score de dépassement OMS : % d'heures > 40 µg/m³ par tronçon
pct_oms = (df[troncons] > SEUIL_OMS_ANNUEL).mean() * 100
nb_pics = (df[troncons] > SEUIL_OMS_HORAIRE).sum()

print(f"\nShape horaire brute : {df.shape}")
print(f"Shape journalière   : {df_jour.shape}")
print(f"Shape mensuelle     : {df_mois.shape}")
print(f"\n% mesures > seuil OMS 40 µg/m³ par tronçon :")
print(pct_oms.round(2).to_string())
print(f"\nNb pics horaires > 200 µg/m³ :")
print(nb_pics.to_string())

# Résumé global (pas d'arrondissement pour NO2 — données Périphérique)
df_resume = pd.DataFrame({
    'troncon'            : troncons,
    'no2_moy_µg_m3'     : df[troncons].mean().round(2).values,
    'no2_max_µg_m3'     : df[troncons].max().round(2).values,
    'pct_heures_oms'    : pct_oms.round(2).values,
    'nb_pics_horaires'  : nb_pics.values,
    'seuil_oms_depasse' : (df[troncons].mean() > SEUIL_OMS_ANNUEL).values,
})
print(f"\nRésumé par tronçon :")
print(df_resume.to_string(index=False))

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
output_dir = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
os.makedirs(output_dir, exist_ok=True)

df.reset_index().to_parquet(os.path.join(output_dir, 'NO2_horaire_silver.parquet'),   index=False)
df_jour.reset_index().to_parquet(os.path.join(output_dir, 'NO2_journalier_silver.parquet'), index=False)
df_mois.reset_index().to_parquet(os.path.join(output_dir, 'NO2_mensuel_silver.parquet'),    index=False)
df_profil.to_parquet(os.path.join(output_dir, 'NO2_profil_horaire_silver.parquet'),         index=False)
df_resume.to_parquet(os.path.join(output_dir, 'NO2_resume_silver.parquet'),                 index=False)

print(f"\n✓ Parquets NO2 créés dans : {output_dir}/")
print(f"  - NO2_horaire_silver.parquet      ({df.shape[0]:,} lignes)")
print(f"  - NO2_journalier_silver.parquet   ({df_jour.shape[0]:,} lignes)")
print(f"  - NO2_mensuel_silver.parquet      ({df_mois.shape[0]:,} lignes)")
print(f"  - NO2_profil_horaire_silver.parquet (24 lignes)")
print(f"  - NO2_resume_silver.parquet       ({len(df_resume)} tronçons)")
