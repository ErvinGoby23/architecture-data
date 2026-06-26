import pandas as pd
import os
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..', '..'))
BRUTE_DIR   = os.path.join(ROOT_DIR, 'architecture-data', 'brute', 'score_de_vivabilite')
FILE        = os.path.join(BRUTE_DIR, 'qualite-de-l-air-exposition-des-parisen-ne-s-au-no2-et-pm2-5.csv')

SILVER_BASE = os.path.join(ROOT_DIR, 'architecture-data', 'silver', 'indicateur3', 'nettoyage-indicateur3')

date_str  = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
ANNEE_REF = 2019

print(f"=== SILVER NO2 — Année : {ANNEE_REF} ===")

# ==========================================================================
# 1. LECTURE
# ==========================================================================
df = pd.read_csv(FILE, sep=';', encoding='utf-8-sig')
df.columns = df.columns.str.strip()
print(f"Shape brute : {df.shape}")
print(f"Années disponibles : {sorted(df['Année'].dropna().unique().astype(int))}")

# ==========================================================================
# 2. FILTRE ANNÉE DE RÉFÉRENCE
# ==========================================================================
row = df[df['Année'] == ANNEE_REF]
if row.empty:
    raise ValueError(f"Année {ANNEE_REF} introuvable dans le fichier")
row = row.iloc[0]

# ==========================================================================
# 3. EXTRACTION PAR ARRONDISSEMENT
# ==========================================================================
arr_cols = [c for c in df.columns if 'ardt' in c.lower() and 'NO2' in c]
assert len(arr_cols) == 20, f"Attendu 20 colonnes arrondissement, trouvé {len(arr_cols)}"

records = []
for i, col in enumerate(arr_cols):
    arr_num = i + 1
    val = row[col]
    records.append({
        'arrondissement'          : arr_num,
        'nb_personnes_exposees_no2': float(val) if pd.notna(val) else None,
        'annee'                   : ANNEE_REF,
    })

df_no2 = pd.DataFrame(records)

# Vérification complétude
nb_null = df_no2['nb_personnes_exposees_no2'].isna().sum()
print(f"Arrondissements renseignés : {20 - nb_null}/20")
if nb_null > 0:
    print(f"Arrondissements manquants : {df_no2[df_no2['nb_personnes_exposees_no2'].isna()]['arrondissement'].tolist()}")

# Métrique globale (pour compatibilité fusion)
global_val = row['Nbre Parisiens soumis à dépassement VR NO2']
df_no2['no2_global_nb_exposes'] = float(global_val) if pd.notna(global_val) else None

print(f"\nAperçu :")
print(df_no2.to_string(index=False))

# ==========================================================================
# 4. EXPORT PARQUET
# ==========================================================================
output_dir = os.path.join(SILVER_BASE, date_str)
os.makedirs(output_dir, exist_ok=True)

out = os.path.join(output_dir, 'NO2_silver.parquet')
df_no2.to_parquet(out, index=False)

print(f"\nParquet : {out}  ({len(df_no2)} arrondissements)")
print(f"Colonnes  : {list(df_no2.columns)}")