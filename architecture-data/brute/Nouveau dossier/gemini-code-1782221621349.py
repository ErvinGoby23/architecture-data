import pandas as pd
from pathlib import Path
import sys

# On remonte jusqu'au dossier racine du projet (architecture-data-projet)
BASE_DIR = Path(__file__).resolve().parent
while BASE_DIR.name != "architecture-data-projet" and BASE_DIR != BASE_DIR.parent:
    BASE_DIR = BASE_DIR.parent

print(f"Dossier racine du projet détecté : {BASE_DIR}")
print("Recherche automatique des fichiers CSV dans le projet...")

def trouver_fichier(nom_fichier):
    resultats = list(BASE_DIR.glob(f"**/{nom_fichier}"))
    if not resultats:
        print(f"❌ ERREUR : Le fichier '{nom_fichier}' est introuvable dans le projet.")
        sys.exit(1)
    print(f"   Trouvé : {resultats[0].relative_to(BASE_DIR)}")
    return resultats[0]

# Localisation des fichiers
path_2023 = trouver_fichier('donnees-sru-data-gouv-maj2023-vf.csv')
path_2024 = trouver_fichier('donnees-sru-data-gouv-maj2024-vf.csv')
path_2025 = trouver_fichier('donnees-sru-data-gouv-2025-v2.csv')

def load_and_clean_2023(filepath):
    # Ajout de encoding='cp1252' pour lire correctement les accents français
    df = pd.read_csv(filepath, sep=',', encoding='cp1252')
    df['Annee_Donnees'] = 2023
    df = df.rename(columns={
        'Code_Departement': 'code_departement',
        'Code_INSEE_commune': 'code_insee_commune',
        'Nom_commune': 'nom_commune',
        'Region': 'region'
    })
    return df

def load_and_clean_2024(filepath):
    # Ajout de encoding='cp1252'
    df = pd.read_csv(filepath, sep=',', header=1, encoding='cp1252')
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df['Annee_Donnees'] = 2024
    df = df.rename(columns={
        'Code_Département': 'code_departement',
        'Code_INSEE_commune': 'code_insee_commune',
        'Nom_commune': 'nom_commune',
        'Region': 'region'
    })
    return df

def load_and_clean_2025(filepath):
    # Ajout de encoding='cp1252'
    df = pd.read_csv(filepath, sep=';', encoding='cp1252')
    df['Annee_Donnees'] = 2025
    df = df.rename(columns={
        'Code_Departement': 'code_departement',
        'Code_INSEE_commune': 'code_insee_commune',
        'Nom_commune': 'nom_commune',
        'Region': 'region'
    })
    return df

print("\n1/3 - Chargement, décodage (cp1252) et nettoyage des fichiers d'origine...")
df23 = load_and_clean_2023(path_2023)
df24 = load_and_clean_2024(path_2024)
df25 = load_and_clean_2025(path_2025)

print("2/3 - Fusion (concaténation longitudinale) des données...")
df_total = pd.concat([df23, df24, df25], ignore_index=True)

cols = ['Annee_Donnees', 'code_insee_commune', 'nom_commune', 'code_departement', 'region']
other_cols = [c for c in df_total.columns if c not in cols]
df_total = df_total[cols + other_cols]

# Le fichier de sortie sera créé au même endroit que ce script
output_file = Path(__file__).resolve().parent / 'donnees_sru_compilees_2023_2025.csv'
print(f"3/3 - Sauvegarde du résultat dans {output_file}...")
df_total.to_csv(output_file, index=False, sep=';', encoding='utf-8-sig')

print("\nTraitement terminé avec succès !")
print(f"-> Nombre total de lignes cumulées : {len(df_total)}")