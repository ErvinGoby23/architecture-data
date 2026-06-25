"""
silver_bruit.py — Nettoyage Bruit (mesures acoustiques Paris)
Score de Vivabilité · Silver layer
"""

import pandas as pd
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
FILE        = os.path.join(BRUTE_DIR, 'bruit.csv')

# ==========================================================================
# 1. LECTURE
# ==========================================================================
df = pd.read_csv(FILE, sep=';', engine='python')
df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
print(f"Shape brute : {df.shape}")

# Renommage colonne année
annee_col = [c for c in df.columns if 'ann' in c.lower()][0]
df = df.rename(columns={annee_col: 'annee'})

# ==========================================================================
# 2. NETTOYAGE
# ==========================================================================
# Conversion en numérique (séparateur ; → virgule possible)
for col in df.columns:
    if col != 'annee':
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')

before = len(df)
df = df.dropna(subset=['annee'])
df['annee'] = df['annee'].astype(int)
print(f"Lignes sans année supprimées : {before - len(df)}")

# Séparation Lden / Ln
lden_cols = [c for c in df.columns if 'lden' in c.lower()]
ln_cols   = [c for c in df.columns if 'ln' in c.lower() and c not in lden_cols and c != 'annee']

print(f"Colonnes Lden : {len(lden_cols)}")
print(f"Colonnes Ln   : {len(ln_cols)}")

# Garder uniquement capteurs < 60% NaN
lden_ok = [c for c in lden_cols if df[c].isnull().mean() < 0.6]
ln_ok   = [c for c in ln_cols   if df[c].isnull().mean() < 0.6]
print(f"Lden exploitables (< 60% NaN) : {len(lden_ok)}")
print(f"Ln   exploitables (< 60% NaN) : {len(ln_ok)}")

cols_keep = ['annee'] + lden_ok + ln_ok
df = df[cols_keep].copy()

# ==========================================================================
# 3. FORMAT LONG + INDICATEURS AGRÉGÉS
# ==========================================================================
# Pivot en format long : une ligne par (annee, capteur)
df_long = df.melt(id_vars='annee', var_name='capteur', value_name='valeur_db').dropna(subset=['valeur_db'])
df_long['type'] = df_long['capteur'].apply(lambda x: 'Lden' if 'lden' in x.lower() else 'Ln')
df_long['capteur_clean'] = (
    df_long['capteur']
    .str.replace(r'(?i) ?[-–]? ?l[dn]en? dB\(A\)', '', regex=True)
    .str.replace(r'(?i)l[dn]en?_bruit routier_', '', regex=True)
    .str.strip()
)

# Agrégation annuelle par type (Lden moyen, Ln moyen) → score vivabilité
SEUIL_LDEN = 68.0  # dB OMS
SEUIL_LN   = 60.0  # dB OMS nuit

df_agg = df_long.groupby(['annee', 'type'])['valeur_db'].agg(
    valeur_moy='mean',
    valeur_min='min',
    valeur_max='max',
    nb_capteurs='count',
).reset_index()
df_agg['depasse_seuil_oms'] = df_agg.apply(
    lambda r: r['valeur_moy'] > SEUIL_LDEN if r['type'] == 'Lden' else r['valeur_moy'] > SEUIL_LN,
    axis=1
)
print(f"\nShape long : {df_long.shape}")
print(f"Shape agrégé annuel : {df_agg.shape}")
print(df_agg.to_string(index=False))

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR  = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilité')
output_dir = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'vivabilite', 'nettoyage-vivabilite')
os.makedirs(output_dir, exist_ok=True)

out_long = os.path.join(output_dir, 'bruit_long_silver.parquet')
out_agg  = os.path.join(output_dir, 'bruit_agrege_silver.parquet')

df_long.to_parquet(out_long, index=False)
df_agg.to_parquet(out_agg,   index=False)

print(f"\n✓ Parquet long    : {out_long}")
print(f"✓ Parquet agrégé  : {out_agg}")
print(f"Shape long finale : {df_long.shape}")
print(f"Colonnes long     : {list(df_long.columns)}")
