"""
fetch_antennes_relais.py — Récupération brute · Antennes relais Paris (VERSION OPTIMISÉE)
Urban Data Explorer
"""

import requests
import json
import time
import os
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor  # <-- On ajoute ça pour le parallélisme

#Config
BASE_URL   = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets"
DATASET    = "antennes-relais"
LIMIT      = 100
OUTPUT_DIR = "../brute/Score-de-connectivite"
URL        = f"{BASE_URL}/{DATASET}/records"

# Génération des variables temporelles
now      = datetime.now()
date_str = now.strftime('%Y-%m-%d')
now_iso  = now.isoformat()

# Dossier et Fichier UNIQUE daté pour la journée
dated_dir = os.path.join(OUTPUT_DIR, date_str)
OUTPUT    = os.path.join(dated_dir, "antennes-relais.json")

# GARDE-FOU : Vérification du double-fetch quotidien
# Si le fichier du jour existe déjà, on arrête le script pour préserver le quota API
if os.path.exists(OUTPUT):
    size_mb = os.path.getsize(OUTPUT) / 1_000_000
    print(f"🛑 [SKIP] Le fetch du jour ({date_str}) a déjà été effectué.")
    print(f"   Fichier existant : {OUTPUT} ({size_mb:.1f} MB)")
    print("   Arrêt du script pour préserver les quotas de l'API.")
    sys.exit(0)

# Helpers
# Interroge l'API pour connaître le nombre total d'antennes disponibles
def count_total() -> int:
    r = requests.get(URL, params={"limit": 1, "offset": 0}, timeout=15)
    r.raise_for_status()
    total = r.json().get("total_count", 0)
    print(f"Total annoncé par l'API : {total}")
    return total

# Récupère une page de résultats à un offset donné (appelée en parallèle)
def fetch_page(offset: int) -> list:
    """Fonction inchangée, mais qui sera appelée en parallèle"""
    params = {"limit": LIMIT, "offset": offset}
    try:
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"❌ Erreur sur l'offset {offset}: {e}")
        return []

#Fetch complet PARALLÈLE 
print(f"🚀 Lancement du Fetch MULTITHREADÉ antennes relais Paris : {date_str}...")
print(f"URL : {URL}\n")

os.makedirs(dated_dir, exist_ok=True)

total = count_total()

# 1. On génère à l'avance tous les offsets nécessaires (ex: 0, 100, 200, 300...)
offsets = list(range(0, total, LIMIT))

all_records = []

# 2. On lance les requêtes en parallèle (max_workers=10 signifie 10 requêtes simultanées)
print(f"⚡ Envoi de {len(offsets)} requêtes en parallèle...")
start_time = time.time()

# Exécute toutes les requêtes de pagination en parallèle (10 threads simultanés)
with ThreadPoolExecutor(max_workers=10) as executor:
    results = executor.map(fetch_page, offsets)

# 3. On rassemble les résultats des différents threads
for batch in results:
    if batch:
        all_records.extend(batch)

end_time = time.time()
print(f"⏱️ Fetch terminé en {end_time - start_time:.2f} secondes.")
print(f"Total collecté : {len(all_records)} antennes")

# 
# LE RESTE DU CODE (Statistiques, Sauvegarde JSON, Métadonnées) RESTE INCHANGÉ
# 
# Statistiques descriptives sur les opérateurs et types de réseau collectés
operateurs   = {}
types_reseau = {}
for r in all_records:
    op = r.get("operateur", "INCONNU")
    operateurs[op] = operateurs.get(op, 0) + 1
    t = r.get("type", "INCONNU")
    types_reseau[t] = types_reseau.get(t, 0) + 1

print("\nOpérateurs :")
for op, count in sorted(operateurs.items(), key=lambda x: -x[1]):
    print(f"  {op:<15} : {count}")

print("\nTypes de réseau :")
for t, count in sorted(types_reseau.items(), key=lambda x: -x[1]):
    print(f"  {str(t):<20} : {count}")

# Sauvegarde du snapshot brut daté en JSON
output_data = {
    "source"        : URL,
    "dataset"       : DATASET,
    "total_count"   : len(all_records),
    "fetched_at"    : now_iso,
    "records"       : all_records,
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"\n💾 Snapshot historique unique créé : {OUTPUT}")

file_size = os.path.getsize(OUTPUT)

# Métadonnées de traçabilité du fetch (statut, taille, total collecté)
metadata = {
    "dataset": DATASET,
    "source": URL,
    "fetched_at": now_iso,
    "total_count": len(all_records),
    "status": "SUCCESS",
    "size_bytes": file_size
}

METADATA_OUTPUT = os.path.join(dated_dir, "fetch_metadata.json")

with open(METADATA_OUTPUT, "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)

print(f"📋 Métadonnées enregistrées        : {METADATA_OUTPUT}")
print(f"Taille                           : {file_size / 1_000_000:.1f} MB")