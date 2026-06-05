"""
load_test_postgresql.py — Tests de charge · Base relationnelle PostgreSQL
Urban Data Explorer · C1.1 Validation performance

Cible : tables gold.score_mobilite et gold.score_connectivite
Méthode : requêtes simultanées via ThreadPoolExecutor
Output : logs console + fichier load_test_results.json
"""

import time
import json
import os
import statistics
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env'))

PG_URL   = os.getenv('PG_URL')
NOW      = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
RESULTS  = []

# ==========================================================================
# REQUÊTES CIBLES (les vraies requêtes de l'API)
# ==========================================================================
QUERIES = {
    "select_all_mobilite": "SELECT * FROM gold.score_mobilite ORDER BY rang",
    "select_all_connectivite": "SELECT * FROM gold.score_connectivite ORDER BY rang",
    "filter_by_code_postal": "SELECT * FROM gold.score_mobilite WHERE code_postal = 75001",
    "top5_mobilite": "SELECT arrondissement, score_mobilite_100, rang FROM gold.score_mobilite ORDER BY rang LIMIT 5",
    "top5_connectivite": "SELECT arrondissement, score_connectivite_100, rang FROM gold.score_connectivite ORDER BY rang LIMIT 5",
    "select_all_silver_mobilite": "SELECT * FROM silver.indicateur_mobilite ORDER BY arrondissement",
    "select_all_silver_connectivite": "SELECT * FROM silver.indicateur_connectivite ORDER BY arrondissement",
    "join_indicateurs": """
        SELECT m.arrondissement, m.score_mobilite_100, c.score_connectivite_100
        FROM gold.score_mobilite m
        JOIN gold.score_connectivite c ON m.arrondissement = c.arrondissement
        ORDER BY m.arrondissement
    """,
}

# ==========================================================================
# FONCTION D'EXÉCUTION D'UNE REQUÊTE
# ==========================================================================
def run_query(query_name: str, sql: str, engine) -> dict:
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "query": query_name,
            "status": "OK",
            "duration_ms": duration_ms,
            "rows": len(rows),
        }
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "query": query_name,
            "status": "ERROR",
            "duration_ms": duration_ms,
            "error": str(e),
            "rows": 0,
        }

# ==========================================================================
# TEST 1 — LATENCE DE BASE (1 requête à la fois)
# ==========================================================================
def test_latence(engine):
    print("\n--- TEST 1 : Latence de base (séquentiel) ---")
    results = []
    for name, sql in QUERIES.items():
        r = run_query(name, sql, engine)
        results.append(r)
        status = "OK" if r["status"] == "OK" else "ERREUR"
        print(f"  [{status}] {name:<35} {r['duration_ms']:>8.2f} ms  ({r['rows']} lignes)")
    return results

# ==========================================================================
# TEST 2 — CHARGE SIMULTANÉE (N connexions en parallèle)
# ==========================================================================
def test_charge(engine, nb_workers: int, nb_iterations: int):
    print(f"\n--- TEST 2 : Charge simultanée ({nb_workers} workers x {nb_iterations} itérations) ---")

    tasks = []
    for _ in range(nb_iterations):
        for name, sql in QUERIES.items():
            tasks.append((name, sql))

    durations = []
    errors    = 0

    start_global = time.perf_counter()

    with ThreadPoolExecutor(max_workers=nb_workers) as executor:
        futures = [executor.submit(run_query, name, sql, engine) for name, sql in tasks]
        for future in as_completed(futures):
            r = future.result()
            if r["status"] == "OK":
                durations.append(r["duration_ms"])
            else:
                errors += 1

    total_time = round((time.perf_counter() - start_global) * 1000, 2)

    if durations:
        stats = {
            "nb_workers":    nb_workers,
            "nb_requetes":   len(tasks),
            "nb_erreurs":    errors,
            "total_ms":      total_time,
            "min_ms":        round(min(durations), 2),
            "max_ms":        round(max(durations), 2),
            "moyenne_ms":    round(statistics.mean(durations), 2),
            "mediane_ms":    round(statistics.median(durations), 2),
            "p95_ms":        round(sorted(durations)[int(len(durations) * 0.95)], 2),
        }
        print(f"  Requêtes totales  : {len(tasks)} ({errors} erreurs)")
        print(f"  Temps total       : {total_time} ms")
        print(f"  Latence min/moy/max : {stats['min_ms']} / {stats['moyenne_ms']} / {stats['max_ms']} ms")
        print(f"  Médiane           : {stats['mediane_ms']} ms")
        print(f"  P95               : {stats['p95_ms']} ms")
    else:
        stats = {"nb_workers": nb_workers, "nb_erreurs": errors, "nb_requetes": len(tasks)}
        print("  Aucun résultat valide.")

    return stats

# ==========================================================================
# MAIN
# ==========================================================================
if __name__ == "__main__":
    print(f"=== LOAD TEST POSTGRESQL — Urban Data Explorer ===")
    print(f"Date : {NOW}")
    print(f"Cibles : gold.score_mobilite, gold.score_connectivite")

    if not PG_URL:
        raise EnvironmentError("PG_URL non défini dans le .env")

    engine = create_engine(PG_URL, pool_size=20, max_overflow=10)

    # Test 1 — latence séquentielle
    latence_results = test_latence(engine)

    # Test 2 — 10 workers (charge légère)
    charge_10 = test_charge(engine, nb_workers=10, nb_iterations=3)

    # Test 3 — 50 workers (charge modérée)
    charge_50 = test_charge(engine, nb_workers=50, nb_iterations=2)

    # Test 4 — 100 workers (pic de charge)
    charge_100 = test_charge(engine, nb_workers=100, nb_iterations=1)

    # ==========================================================================
    # EXPORT JSON
    # ==========================================================================
    output = {
        "meta": {
            "date": NOW,
            "pg_url": PG_URL.split("@")[-1],  # masque le mot de passe
            "tables_testees": ["gold.score_mobilite", "gold.score_connectivite"],
        },
        "test_latence_base": latence_results,
        "test_charge_10_workers":  charge_10,
        "test_charge_50_workers":  charge_50,
        "test_charge_100_workers": charge_100,
    }


    date_folder = datetime.now().strftime('%Y-%m-%d')
    hour_folder = datetime.now().strftime('%H-%M-%S')
    output_dir  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', date_folder, hour_folder)
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "load_test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Résultats exportés : {output_path}")
    print("=== LOAD TEST TERMINE ===")