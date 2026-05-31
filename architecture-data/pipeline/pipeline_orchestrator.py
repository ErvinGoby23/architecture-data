"""
pipeline_orchestrator.py — Orchestrateur Centralisé (Batch Quotidien - Version Date-Aware Corrigée)
Urban Data Explorer · Bronze -> Silver -> Gold
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from prefect import flow, task, get_run_logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

# ==========================================================================
# UTILITAIRES
# ==========================================================================
def run_script(path: str, arg: str = None) -> float:
    """Lance un script Python avec le même Python que le venv courant, avec un argument optionnel."""
    start = time.time()
    cmd = [sys.executable, path]
    if arg:
        cmd.append(arg)
    subprocess.run(cmd, check=True, cwd=os.path.dirname(path))
    return round(time.time() - start, 1)

def file_size_mb(path: str) -> float:
    """Retourne la taille d'un fichier en MB."""
    return round(os.path.getsize(path) / 1_000_000, 2) if os.path.exists(path) else 0

# ==========================================================================
# BRONZE
# ==========================================================================
@task(name="Bronze - Fetch stationnement", retries=2, retry_delay_seconds=60)
def run_bronze_stationnement(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fetch stationnement pour {date_str}")
    script = os.path.join(BASE_DIR, "fetch_stationnement.py")
    duration = run_script(script, date_str)
    dated_file = os.path.join(ROOT_DIR, "brute", "indicateur-Score-accessibilité-mobilité",
                              date_str, "stationnement-voie-publique-emplacements.json")
    size_mb = file_size_mb(dated_file)
    skipped = duration < 3.0
    if skipped:
        logger.warning(f"SKIP — fichier du jour déjà présent ({size_mb} MB)")
    else:
        logger.info(f"Fetch OK en {duration}s — {size_mb} MB")
    return {"duration": duration, "size_mb": size_mb, "skipped": skipped}


@task(name="Bronze - Fetch antennes relais", retries=2, retry_delay_seconds=60)
def run_bronze_antennes(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fetch antennes relais pour {date_str}")
    script = os.path.join(BASE_DIR, "fetch_antennes_relais.py")
    duration = run_script(script, date_str)
    dated_file = os.path.join(ROOT_DIR, "brute", "Score-de-connectivite",
                              date_str, "antennes-relais.json")
    size_mb = file_size_mb(dated_file)
    skipped = duration < 3.0
    if skipped:
        logger.warning(f"SKIP — fichier du jour déjà présent ({size_mb} MB)")
    else:
        logger.info(f"Fetch OK en {duration}s — {size_mb} MB")
    return {"duration": duration, "size_mb": size_mb, "skipped": skipped}

# ==========================================================================
# SILVER & GOLD TASKS
# ==========================================================================
@task(name="Silver - Arrets lignes", retries=1)
def run_silver_arrets(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver arrêts lignes — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_arrets_lignes.py")
    duration = run_script(script, date_str)
    logger.info(f"Terminé en {duration}s")
    return duration

@task(name="Silver - Bornes taxi", retries=1)
def run_silver_taxi(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver bornes taxi — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_bornes_taxi.py")
    duration = run_script(script, date_str)
    logger.info(f"Terminé en {duration}s")
    return duration

@task(name="Silver - Stationnement", retries=1)
def run_silver_stationnement(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver stationnement — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_stationnement.py")
    duration = run_script(script, date_str)
    if duration > 60:
        logger.warning(f"Stationnement anormalement lent : {duration}s")
    else:
        logger.info(f"Terminé en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 1", retries=1)
def run_silver_fusion_ind1(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fusion Silver ind1 — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur1", "silver_fusion.py")
    duration = run_script(script, date_str)
    logger.info(f"Fusion ind1 OK en {duration}s")
    return duration

@task(name="Silver - Antennes relais", retries=1)
def run_silver_antennes_s(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver antennes relais — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur2", "transform_antennes_silver.py")
    duration = run_script(script, date_str)
    logger.info(f"Terminé en {duration}s")
    return duration

@task(name="Silver - Fibre", retries=1)
def run_silver_fibre(date_str: str):
    logger = get_run_logger()
    logger.info(f"Silver fibre — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur2", "transform_fibre_silver.py")
    duration = run_script(script, date_str)
    logger.info(f"Terminé en {duration}s")
    return duration

@task(name="Silver - Fusion indicateur 2", retries=1)
def run_silver_fusion_ind2(date_str: str):
    logger = get_run_logger()
    logger.info(f"Fusion Silver ind2 — {date_str}")
    script = os.path.join(ROOT_DIR, "silver", "indicateur2", "silver_connectivite_fusion.py")
    duration = run_script(script, date_str)
    logger.info(f"Fusion ind2 OK en {duration}s")
    return duration

@task(name="Gold - Score mobilite", retries=1)
def run_gold_mobilite(date_str: str):
    logger = get_run_logger()
    logger.info(f"Gold score mobilité — {date_str}")
    script = os.path.join(ROOT_DIR, "gold", "indicateur1", "gold_score_mobilite.py")
    duration = run_script(script, date_str)
    logger.info(f"Gold mobilité OK en {duration}s")
    return duration

@task(name="Gold - Score connectivite", retries=1)
def run_gold_connectivite(date_str: str):
    logger = get_run_logger()
    logger.info(f"Gold score connectivité — {date_str}")
    script = os.path.join(ROOT_DIR, "gold", "indicateur2", "gold_score_connectivite.py")
    duration = run_script(script, date_str)
    logger.info(f"Gold connectivité OK en {duration}s")
    return duration

# ==========================================================================
# FLOW PRINCIPAL
# ==========================================================================
@flow(name="Urban Data Explorer — Main Daily Batch")
def main_pipeline():
    logger = get_run_logger()
    global_start = time.time()

    current_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"=== DEMARRAGE DU BATCH POUR LA DATE : {current_date} ===")

    # BRONZE en parallèle
    future_stat = run_bronze_stationnement.submit(current_date)
    future_ant  = run_bronze_antennes.submit(current_date)
    perf_stat   = future_stat.result()
    perf_ant    = future_ant.result()
    logger.info("Bronze OK")

    # SILVER ind1 en parallèle
    future_arrets = run_silver_arrets.submit(current_date)
    future_taxi   = run_silver_taxi.submit(current_date)
    future_stat_s = run_silver_stationnement.submit(current_date)

    # SILVER ind2 en parallèle — lancés SANS attendre ind1
    future_ant_s  = run_silver_antennes_s.submit(current_date)
    future_fibre  = run_silver_fibre.submit(current_date)

    # On attend TOUT le monde
    future_arrets.result()
    future_taxi.result()
    future_stat_s.result()
    future_ant_s.result()
    future_fibre.result()
    logger.info("Silver OK")

    # FUSIONS en parallèle
    future_fusion1 = run_silver_fusion_ind1.submit(current_date)
    future_fusion2 = run_silver_fusion_ind2.submit(current_date)
    future_fusion1.result()
    future_fusion2.result()
    logger.info("Fusions OK")

    # GOLD en parallèle
    future_mob  = run_gold_mobilite.submit(current_date)
    future_conn = run_gold_connectivite.submit(current_date)
    future_mob.result()
    future_conn.result()
    logger.info("Gold OK")

    # RAPPORT DE PERFORMANCE (C2.4)
    total_duration = round(time.time() - global_start, 1)
    total_volume   = round(perf_stat["size_mb"] + perf_ant["size_mb"], 2)
    bronze_skipped = perf_stat.get("skipped", False) or perf_ant.get("skipped", False)
    debit_mbs      = round(total_volume / total_duration, 2) if total_duration > 0 else 0

    logger.info("=== RAPPORT DE PERFORMANCE (C2.4) ===")
    logger.info(f"Temps total d'exécution : {total_duration}s")
    logger.info(f"Volume des fichiers du jour : {total_volume} MB")
    logger.info(f"Débit moyen             : {debit_mbs} MB/s")
    logger.info(f"Comportement ce jour    : {'SKIP FETCH' if bronze_skipped else 'FETCH OK'}")
    logger.info("Base PostgreSQL         : Schémas silver et gold mis à jour")
    logger.info("=====================================")


if __name__ == "__main__":
    main_pipeline.serve(
        name="daily-urban-explorer-sync",
        cron="0 3 * * *"
    )