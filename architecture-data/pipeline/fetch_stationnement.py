"""
fetch_stationnement.py — Récupération brute · Stationnement voie publique (CORRIGÉ APIS)
Urban Data Explorer

Source  : API Open Data Paris (Opendatasoft v2.1)
Dataset : stationnement-voie-publique-emplacements
"""

import requests
import json
import time
import os
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Config -
BASE_URL       = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets"
DATASET        = "stationnement-voie-publique-emplacements"
LIMIT          = 100  
OUTPUT_DIR     = "../brute/indicateur-Score-accessibilité-mobilité"
URL            = f"{BASE_URL}/{DATASET}/records"

now      = datetime.now()
date_str = now.strftime('%Y-%m-%d')
now_iso  = now.isoformat()

dated_dir = os.path.join(OUTPUT_DIR, date_str)
OUTPUT    = os.path.join(dated_dir, "stationnement-voie-publique-emplacements.json")

# GARDE-FOU
if os.path.exists(OUTPUT):
    print(f"🛑 [SKIP] Le fetch du jour ({date_str}) pour le Stationnement a déjà été effectué.")
    sys.exit(0)

# Helpers 
def count_records_arrond(arrond: int) -> int:
    """Compte le nombre de lignes pour un arrondissement spécifique"""
    params = {"limit": 1, "offset": 0, "where": f"arrond={arrond}"}
    try:
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("total_count", 0)
    except Exception as e:
        print(f"❌ Impossible de compter l'arrondissement {arrond}: {e}")
        return 0

def fetch_page_arrond(args) -> list:
    """Va chercher une page spécifique pour un arrondissement donné"""
    arrond, offset = args
    params = {"limit": LIMIT, "offset": offset, "where": f"arrond={arrond}"}
    try:
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"❌ Erreur [Arrond {arrond:02d} | Offset {offset}]: {e}")
        return []

# Execution Globale Parallèle 
print(f"🚀 Lancement du Fetch stationnement Paris (Hybrid Multi-threaded) : {date_str}...")

os.makedirs(dated_dir, exist_ok=True)
start_time = time.time()

print("📊 Planification des requêtes par arrondissement...")
totaux = {arrond: count_records_arrond(arrond) for arrond in range(1, 21)}
for arrond, total in totaux.items():
    print(f"  [Arrond {arrond:02d}] {total} lignes détectées.")

tasks_to_run = [
    (arrond, offset)
    for arrond, total in totaux.items()
    for offset in range(0, total, LIMIT)
]

all_records = []

print(f"\n⚡ Envoi de {len(tasks_to_run)} requêtes ciblées en parallèle...")

with ThreadPoolExecutor(max_workers=3) as executor:
    results = executor.map(fetch_page_arrond, tasks_to_run)

for batch in results:
    if batch:
        all_records.extend(batch)

end_time = time.time()
print(f"\n⏱️ Fetch stationnement terminé proprement en {end_time - start_time:.2f} secondes.")
print(f"Total brut collecté : {len(all_records):,} enregistrements")

# SAUVEGARDE ET METADONNEES
output_data = {
    "source"        : URL,
    "dataset"       : DATASET,
    "total_count"   : len(all_records),
    "fetched_at"    : now_iso,
    "records"       : all_records
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"\n💾 Snapshot historique unique créé : {OUTPUT}")

file_size = os.path.getsize(OUTPUT)

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