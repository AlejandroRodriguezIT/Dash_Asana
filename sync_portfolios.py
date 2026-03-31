"""
Sincronización de Portafolios de Asana
=======================================
Obtiene los portafolios y sus proyectos desde la API de Asana
y los almacena en la tabla `portfolio_projects` de MySQL.
Proyectos sin portafolio reciben el valor 'Otros'.
"""

import requests
import time
from sqlalchemy import text
from database import get_engine, query_to_df

# Configuración API Asana
ASANA_PAT = "2/1209922584031813/1213507360843176:24023a0a03bb07989c1a46593f363bec"
ASANA_BASE = "https://app.asana.com/api/1.0"
ASANA_WORKSPACE_GID = "60002580153529"
HEADERS = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}


def _fetch_all_portfolios():
    """Obtiene todos los portafolios del workspace iterando por usuario."""
    print("Obteniendo usuarios del workspace...")
    r = requests.get(
        f"{ASANA_BASE}/users",
        headers=HEADERS,
        params={"workspace": ASANA_WORKSPACE_GID, "opt_fields": "name,email"},
    )
    r.raise_for_status()
    users = r.json().get("data", [])
    print(f"  {len(users)} usuarios encontrados")

    all_portfolios = {}
    for u in users:
        time.sleep(0.15)
        try:
            r2 = requests.get(
                f"{ASANA_BASE}/portfolios",
                headers=HEADERS,
                params={
                    "workspace": ASANA_WORKSPACE_GID,
                    "owner": u["gid"],
                    "opt_fields": "name,owner,owner.name",
                },
            )
            for p in r2.json().get("data", []):
                if p["gid"] not in all_portfolios:
                    all_portfolios[p["gid"]] = {
                        "name": p["name"],
                        "owner": p.get("owner", {}).get("name", "?"),
                    }
        except Exception:
            pass

    print(f"  {len(all_portfolios)} portafolios encontrados")
    return all_portfolios


def _fetch_portfolio_items(portfolio_gid):
    """Obtiene los proyectos dentro de un portafolio."""
    r = requests.get(
        f"{ASANA_BASE}/portfolios/{portfolio_gid}/items",
        headers=HEADERS,
        params={"opt_fields": "name,resource_type"},
    )
    r.raise_for_status()
    return [
        item
        for item in r.json().get("data", [])
        if item.get("resource_type") == "project"
    ]


def sync():
    """Sincroniza portafolios desde Asana y actualiza la tabla portfolio_projects."""
    engine = get_engine()

    # 1. Crear tabla si no existe
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS portfolio_projects (
                project_gid VARCHAR(50) PRIMARY KEY,
                portfolio_name VARCHAR(200) NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

    # 2. Obtener portafolios y sus proyectos desde la API
    portfolios = _fetch_all_portfolios()
    portfolio_map = {}  # project_gid -> portfolio_name

    for p_gid, p_info in portfolios.items():
        time.sleep(0.15)
        items = _fetch_portfolio_items(p_gid)
        print(f"  Portafolio '{p_info['name']}': {len(items)} proyectos")
        for item in items:
            portfolio_map[item["gid"]] = p_info["name"]

    # 3. Obtener todos los proyectos activos de la BD
    df_projects = query_to_df(
        "SELECT gid FROM projects WHERE archived = 0 "
        "AND name NOT LIKE 'Tareas previamente asignadas%%'"
    )

    # 4. Asignar 'Otros' a proyectos sin portafolio
    for _, row in df_projects.iterrows():
        if row["gid"] not in portfolio_map:
            portfolio_map[row["gid"]] = "Otros"

    # 5. Insertar/actualizar en la tabla
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM portfolio_projects"))
        for project_gid, portfolio_name in portfolio_map.items():
            conn.execute(
                text(
                    "INSERT INTO portfolio_projects (project_gid, portfolio_name) "
                    "VALUES (:gid, :name) "
                    "ON DUPLICATE KEY UPDATE portfolio_name = :name"
                ),
                {"gid": project_gid, "name": portfolio_name},
            )
        conn.commit()

    print(f"\n=== Sincronización completada ===")
    print(f"  Total proyectos mapeados: {len(portfolio_map)}")
    for name in sorted(set(portfolio_map.values())):
        count = sum(1 for v in portfolio_map.values() if v == name)
        print(f"  {name}: {count} proyectos")


if __name__ == "__main__":
    sync()
