"""
Conexión a la base de datos MySQL - Asana
==========================================
RC Deportivo de La Coruña - Gestión de Proyectos
"""

import pandas as pd
from sqlalchemy import create_engine, text

# Configuración MySQL (base de datos Asana)
MYSQL_CONFIG = {
    "user": "alen_depor",
    "password": "ik3QJOq6n",
    "host": "82.165.192.201",
    "database": "Asana"
}

MYSQL_URL = (
    f"mysql+pymysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}"
    f"@{MYSQL_CONFIG['host']}/{MYSQL_CONFIG['database']}"
)

_engine = None


def get_engine():
    """Crea y devuelve un engine de SQLAlchemy reutilizable."""
    global _engine
    if _engine is None:
        _engine = create_engine(MYSQL_URL, pool_pre_ping=True)
    return _engine


def query_to_df(query: str, params: dict = None) -> pd.DataFrame:
    """Ejecuta una query y devuelve un DataFrame."""
    engine = get_engine()
    return pd.read_sql(text(query), engine, params=params)


# =============================================================================
# AUTENTICACIÓN
# =============================================================================

def init_users_table():
    """Crea la tabla de usuarios si no existe e inserta admin por defecto."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS plataforma_usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario VARCHAR(100) UNIQUE NOT NULL,
                contrasena VARCHAR(255) NOT NULL,
                permisos VARCHAR(50) NOT NULL DEFAULT '0',
                nombre VARCHAR(200),
                rol VARCHAR(100),
                activo TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        result = conn.execute(
            text("SELECT COUNT(*) AS cnt FROM plataforma_usuarios WHERE usuario = 'admin'")
        )
        if result.fetchone()[0] == 0:
            conn.execute(text(
                "INSERT INTO plataforma_usuarios (usuario, contrasena, permisos, nombre, rol) "
                "VALUES ('admin', 'admin', '0', 'Administrador', 'Dirección')"
            ))
        conn.commit()


def validate_user(usuario: str, contrasena: str):
    """Valida credenciales. Devuelve dict con info del usuario o None."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id, usuario, permisos, nombre, rol FROM plataforma_usuarios "
            "WHERE usuario = :u AND contrasena = :p AND activo = 1"
        ), {"u": usuario, "p": contrasena})
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "usuario": row[1],
                "permisos": row[2],
                "nombre": row[3],
                "rol": row[4],
            }
    return None


# =============================================================================
# QUERIES — VISIÓN GLOBAL
# =============================================================================

# Filtro común: excluir proyectos archivados, 'Tareas previamente asignadas' y vacíos
_PROJ_FILTER = """
    p.archived = 0
    AND p.name NOT LIKE 'Tareas previamente asignadas%%'
    AND (SELECT COUNT(*) FROM task_projects tp
         JOIN tasks t ON tp.task_gid = t.gid
         WHERE tp.project_gid = p.gid AND t.parent_gid IS NULL) > 0
"""


def get_active_projects_count():
    """Número total de proyectos activos (no archivados, no vacíos)."""
    return query_to_df(f"""
        SELECT COUNT(*) AS total FROM projects p WHERE {_PROJ_FILTER}
    """)


def get_projects_by_month():
    """
    Proyectos agrupados por mes de fecha de entrega (due_on).
    Devuelve mes (YYYY-MM) y total.
    Los proyectos sin fecha se agrupan como 'Sin Fecha de Entrega'.
    """
    return query_to_df("""
        SELECT
            CASE
                WHEN due_on IS NOT NULL
                THEN DATE_FORMAT(due_on, '%%Y-%%m')
                ELSE 'sin_fecha'
            END AS mes,
            COUNT(*) AS total
        FROM projects
        WHERE archived = 0
          AND name NOT LIKE 'Tareas previamente asignadas%%'
        GROUP BY mes
        ORDER BY
            CASE WHEN mes = 'sin_fecha' THEN 1 ELSE 0 END,
            mes
    """)


def get_projects_per_owner():
    """Número de proyectos activos por owner_name (carga de trabajo)."""
    return query_to_df(f"""
        SELECT
            COALESCE(p.owner_name, 'Sin asignar') AS owner_name,
            COUNT(*) AS total
        FROM projects p
        WHERE {_PROJ_FILTER}
        GROUP BY p.owner_name
        ORDER BY total DESC
    """)


def get_projects_per_member():
    """
    Número de proyectos en los que participa cada colaborador.
    Solo muestra colaboradores con más de 1 proyecto.
    Excluye proyectos vacíos y 'Tareas previamente asignadas'.
    """
    return query_to_df(f"""
        SELECT
            pm.user_name,
            COUNT(DISTINCT pm.project_gid) AS total
        FROM project_memberships pm
        JOIN projects p ON pm.project_gid = p.gid
        WHERE {_PROJ_FILTER}
          AND pm.user_name IS NOT NULL
        GROUP BY pm.user_name
        HAVING total > 1
        ORDER BY total DESC
    """)


def get_projects_for_month(mes: str):
    """
    Proyectos con fecha de entrega en un mes concreto.
    mes = 'YYYY-MM' o 'sin_fecha'.
    """
    if mes == "sin_fecha":
        return query_to_df("""
            SELECT p.gid, p.name, p.owner_name, p.team_name,
                   p.created_at, p.due_on, p.start_on,
                   p.notes, p.permalink_url, p.color,
                   (SELECT COUNT(*) FROM task_projects tp
                    JOIN tasks t ON tp.task_gid = t.gid
                    WHERE tp.project_gid = p.gid AND t.completed = 0
                   ) AS tareas_pendientes,
                   (SELECT COUNT(*) FROM task_projects tp
                    JOIN tasks t ON tp.task_gid = t.gid
                    WHERE tp.project_gid = p.gid AND t.completed = 1
                   ) AS tareas_completadas
            FROM projects p
            WHERE p.archived = 0
              AND p.due_on IS NULL
            ORDER BY p.name
        """)
    else:
        return query_to_df(
            """
            SELECT p.gid, p.name, p.owner_name, p.team_name,
                   p.created_at, p.due_on, p.start_on,
                   p.notes, p.permalink_url, p.color,
                   (SELECT COUNT(*) FROM task_projects tp
                    JOIN tasks t ON tp.task_gid = t.gid
                    WHERE tp.project_gid = p.gid AND t.completed = 0
                   ) AS tareas_pendientes,
                   (SELECT COUNT(*) FROM task_projects tp
                    JOIN tasks t ON tp.task_gid = t.gid
                    WHERE tp.project_gid = p.gid AND t.completed = 1
                   ) AS tareas_completadas
            FROM projects p
            WHERE p.archived = 0
              AND DATE_FORMAT(p.due_on, '%%Y-%%m') = :mes
            ORDER BY p.due_on, p.name
            """,
            params={"mes": mes}
        )


# =============================================================================
# QUERIES — ESTADO DE LOS PROYECTOS
# =============================================================================

def get_all_projects():
    """Todos los proyectos activos con conteo de tareas.
    Excluye 'Tareas previamente asignadas' y proyectos sin tareas."""
    return query_to_df("""
        SELECT * FROM (
            SELECT
                p.gid, p.name, p.owner_name, p.team_name,
                p.created_at, p.modified_at, p.due_on, p.start_on,
                p.notes, p.archived, p.permalink_url, p.color,
                (SELECT COUNT(*) FROM task_projects tp
                 JOIN tasks t ON tp.task_gid = t.gid
                 WHERE tp.project_gid = p.gid AND t.parent_gid IS NULL
                ) AS total_tareas,
                (SELECT COUNT(*) FROM task_projects tp
                 JOIN tasks t ON tp.task_gid = t.gid
                 WHERE tp.project_gid = p.gid AND t.completed = 1 AND t.parent_gid IS NULL
                ) AS tareas_completadas,
                (SELECT COUNT(*) FROM task_projects tp
                 JOIN tasks t ON tp.task_gid = t.gid
                 WHERE tp.project_gid = p.gid AND t.completed = 0 AND t.parent_gid IS NULL
                ) AS tareas_pendientes
            FROM projects p
            WHERE p.archived = 0
              AND p.name NOT LIKE 'Tareas previamente asignadas%%'
            ORDER BY p.name
        ) sub
        WHERE sub.total_tareas > 0
    """)


def get_project_detail(project_gid: str):
    """Detalle de un proyecto concreto."""
    return query_to_df(
        "SELECT * FROM projects WHERE gid = :gid",
        params={"gid": project_gid}
    )


def get_project_sections(project_gid: str):
    """Secciones de un proyecto."""
    return query_to_df(
        "SELECT * FROM sections WHERE project_gid = :gid ORDER BY created_at",
        params={"gid": project_gid}
    )


def get_project_tasks(project_gid: str):
    """
    Tareas de un proyecto (solo nivel principal, no subtareas).
    Incluye sección asignada y custom fields.
    """
    return query_to_df(
        """
        SELECT
            t.gid, t.name, t.assignee_name, t.completed, t.completed_at,
            t.created_at, t.modified_at, t.due_on, t.due_at,
            t.start_on, t.notes, t.num_subtasks, t.parent_gid,
            t.permalink_url,
            ts.section_gid,
            s.name AS section_name
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        LEFT JOIN task_sections ts ON t.gid = ts.task_gid
        LEFT JOIN sections s ON ts.section_gid = s.gid AND s.project_gid = :gid
        WHERE tp.project_gid = :gid
          AND t.parent_gid IS NULL
        ORDER BY s.created_at, t.created_at
        """,
        params={"gid": project_gid}
    )


def get_task_subtasks(task_gid: str):
    """Subtareas de una tarea."""
    return query_to_df(
        """
        SELECT gid, name, assignee_name, completed, completed_at,
               due_on, notes, num_subtasks, permalink_url
        FROM tasks
        WHERE parent_gid = :gid
        ORDER BY created_at
        """,
        params={"gid": task_gid}
    )


def get_task_custom_fields(task_gid: str):
    """Valores de custom fields de una tarea."""
    return query_to_df(
        """
        SELECT custom_field_name, display_value, text_value,
               number_value, enum_value_name
        FROM task_custom_field_values
        WHERE task_gid = :gid
          AND (display_value IS NOT NULL OR text_value IS NOT NULL
               OR number_value IS NOT NULL OR enum_value_name IS NOT NULL)
        """,
        params={"gid": task_gid}
    )


def get_project_members(project_gid: str):
    """Miembros de un proyecto."""
    return query_to_df(
        """
        SELECT user_name, access_level
        FROM project_memberships
        WHERE project_gid = :gid
        ORDER BY user_name
        """,
        params={"gid": project_gid}
    )


def get_owners_list():
    """Lista de owners únicos de proyectos activos."""
    return query_to_df("""
        SELECT DISTINCT COALESCE(owner_name, 'Sin asignar') AS owner_name
        FROM projects
        WHERE archived = 0
        ORDER BY owner_name
    """)


def get_teams_list():
    """Lista de equipos únicos de proyectos activos."""
    return query_to_df("""
        SELECT DISTINCT COALESCE(team_name, 'Sin equipo') AS team_name
        FROM projects
        WHERE archived = 0
        ORDER BY team_name
    """)


# =============================================================================
# QUERIES — VISIÓN GLOBAL: ESTADÍSTICAS Y PRESUPUESTOS
# =============================================================================

def get_global_task_stats():
    """Estadísticas globales de tareas: total, completadas, pendientes."""
    return query_to_df(f"""
        SELECT
            COUNT(*) AS total_tareas,
            SUM(CASE WHEN t.completed = 1 THEN 1 ELSE 0 END) AS completadas,
            SUM(CASE WHEN t.completed = 0 THEN 1 ELSE 0 END) AS pendientes
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE t.parent_gid IS NULL
          AND {_PROJ_FILTER}
    """)


def get_budget_by_team():
    """Presupuesto total por equipo (suma de Presupuesto sin IVA + Gasto Anual)."""
    return query_to_df(f"""
        SELECT
            COALESCE(p.team_name, 'Sin equipo') AS team_name,
            SUM(tcf.number_value) AS total_presupuesto
        FROM task_custom_field_values tcf
        JOIN tasks t ON tcf.task_gid = t.gid
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE tcf.custom_field_name IN ('Presupuesto sin IVA', 'Gasto Anual')
          AND tcf.number_value IS NOT NULL
          AND tcf.number_value > 0
          AND {_PROJ_FILTER}
        GROUP BY p.team_name
        ORDER BY total_presupuesto DESC
    """)


def get_budget_by_project(team_name: str):
    """Presupuesto desglosado por proyecto dentro de un equipo."""
    return query_to_df(f"""
        SELECT
            p.gid AS project_gid,
            p.name AS project_name,
            SUM(tcf.number_value) AS total_presupuesto
        FROM task_custom_field_values tcf
        JOIN tasks t ON tcf.task_gid = t.gid
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE tcf.custom_field_name IN ('Presupuesto sin IVA', 'Gasto Anual')
          AND tcf.number_value IS NOT NULL
          AND tcf.number_value > 0
          AND {_PROJ_FILTER}
          AND COALESCE(p.team_name, 'Sin equipo') = :team_name
        GROUP BY p.gid, p.name
        ORDER BY total_presupuesto DESC
    """, params={"team_name": team_name})


def get_budget_by_task(project_gid: str):
    """Presupuesto desglosado por tarea dentro de un proyecto."""
    return query_to_df("""
        SELECT
            t.gid AS task_gid,
            t.name AS task_name,
            t.assignee_name,
            tcf.custom_field_name,
            tcf.number_value AS presupuesto
        FROM task_custom_field_values tcf
        JOIN tasks t ON tcf.task_gid = t.gid
        JOIN task_projects tp ON t.gid = tp.task_gid
        WHERE tcf.custom_field_name IN ('Presupuesto sin IVA', 'Gasto Anual')
          AND tcf.number_value IS NOT NULL
          AND tcf.number_value > 0
          AND tp.project_gid = :gid
          AND t.parent_gid IS NULL
        ORDER BY tcf.number_value DESC
    """, params={"gid": project_gid})


def get_delegated_tasks_detail(owner_name: str, assignee_name: str):
    """Detalle de tareas delegadas a una persona en proyectos del responsable."""
    return query_to_df("""
        SELECT
            t.gid, t.name AS task_name, t.due_on, t.created_at,
            t.permalink_url, t.num_subtasks,
            p.name AS project_name, p.gid AS project_gid
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE p.owner_name = :owner
          AND p.archived = 0
          AND t.completed = 0
          AND t.parent_gid IS NULL
          AND t.assignee_name = :assignee
        ORDER BY t.due_on IS NULL, t.due_on, t.name
    """, params={"owner": owner_name, "assignee": assignee_name})


# =============================================================================
# QUERIES — TAREAS PRIORITARIAS
# =============================================================================

def get_priority_tasks():
    """
    Tareas pendientes con fecha de entrega, clasificadas en:
      - overdue: fecha pasada
      - this_week: entre hoy y el domingo de esta semana
      - next_week: lunes a domingo de la semana siguiente
    Excluye proyectos 'Tareas previamente asignadas'.
    """
    return query_to_df("""
        SELECT
            t.gid,
            t.name AS task_name,
            t.assignee_name,
            t.due_on,
            t.due_at,
            t.permalink_url,
            t.num_subtasks,
            p.name AS project_name,
            p.gid  AS project_gid,
            p.owner_name,
            p.team_name,
            CASE
                WHEN t.due_on < CURDATE()
                    THEN 'overdue'
                WHEN t.due_on BETWEEN CURDATE()
                    AND DATE_ADD(
                        CURDATE(),
                        INTERVAL (6 - WEEKDAY(CURDATE())) DAY
                    )
                    THEN 'this_week'
                WHEN t.due_on BETWEEN
                    DATE_ADD(
                        CURDATE(),
                        INTERVAL (7 - WEEKDAY(CURDATE())) DAY
                    )
                    AND DATE_ADD(
                        CURDATE(),
                        INTERVAL (13 - WEEKDAY(CURDATE())) DAY
                    )
                    THEN 'next_week'
                ELSE NULL
            END AS priority_bucket
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE t.completed = 0
          AND t.parent_gid IS NULL
          AND t.due_on IS NOT NULL
          AND p.archived = 0
          AND p.name NOT LIKE 'Tareas previamente asignadas%%'
          AND t.due_on <= DATE_ADD(
                CURDATE(),
                INTERVAL (13 - WEEKDAY(CURDATE())) DAY
          )
        ORDER BY t.due_on, t.name
    """)


# =============================================================================
# QUERIES — FICHA RESPONSABLE
# =============================================================================

def get_projects_for_owner(owner_name: str):
    """Proyectos asignados a un responsable con conteo de tareas.
    Excluye proyectos vacíos y 'Tareas previamente asignadas'."""
    return query_to_df(
        f"""
        SELECT * FROM (
            SELECT
                p.gid, p.name, p.team_name, p.due_on, p.start_on,
                p.created_at, p.modified_at, p.notes, p.permalink_url,
                (SELECT COUNT(*) FROM task_projects tp
                 JOIN tasks t ON tp.task_gid = t.gid
                 WHERE tp.project_gid = p.gid AND t.parent_gid IS NULL
                ) AS total_tareas,
                (SELECT COUNT(*) FROM task_projects tp
                 JOIN tasks t ON tp.task_gid = t.gid
                 WHERE tp.project_gid = p.gid AND t.completed = 1 AND t.parent_gid IS NULL
                ) AS tareas_completadas,
                (SELECT COUNT(*) FROM task_projects tp
                 JOIN tasks t ON tp.task_gid = t.gid
                 WHERE tp.project_gid = p.gid AND t.completed = 0 AND t.parent_gid IS NULL
                ) AS tareas_pendientes
            FROM projects p
            WHERE {_PROJ_FILTER}
              AND p.owner_name = :owner
            ORDER BY p.due_on IS NULL, p.due_on, p.name
        ) sub
        WHERE sub.total_tareas > 0
        """,
        params={"owner": owner_name}
    )


def get_owner_pending_tasks(owner_name: str):
    """
    Tareas pendientes en proyectos de un responsable,
    ordenadas por fecha de entrega (más urgentes primero).
    """
    return query_to_df(
        """
        SELECT
            t.gid, t.name AS task_name, t.assignee_name,
            t.due_on, t.due_at, t.created_at,
            t.num_subtasks, t.permalink_url,
            p.name AS project_name, p.gid AS project_gid
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE p.owner_name = :owner
          AND p.archived = 0
          AND t.completed = 0
          AND t.parent_gid IS NULL
        ORDER BY t.due_on IS NULL, t.due_on, t.created_at
        """,
        params={"owner": owner_name}
    )


def get_owner_delegated_pending(owner_name: str):
    """
    Tareas pendientes en proyectos del responsable que están asignadas
    a OTRAS personas (tareas delegadas sin completar).
    """
    return query_to_df(
        """
        SELECT
            t.assignee_name,
            COUNT(*) AS tareas_pendientes,
            MIN(t.due_on) AS deadline_mas_cercano
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE p.owner_name = :owner
          AND p.archived = 0
          AND t.completed = 0
          AND t.parent_gid IS NULL
          AND t.assignee_name IS NOT NULL
          AND t.assignee_name != :owner
        GROUP BY t.assignee_name
        ORDER BY tareas_pendientes DESC
        """,
        params={"owner": owner_name}
    )


def get_owner_tasks_by_status(owner_name: str):
    """Resumen de tareas completadas vs pendientes por proyecto del responsable."""
    return query_to_df(
        """
        SELECT
            p.name AS project_name,
            SUM(CASE WHEN t.completed = 1 THEN 1 ELSE 0 END) AS completadas,
            SUM(CASE WHEN t.completed = 0 THEN 1 ELSE 0 END) AS pendientes
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE p.owner_name = :owner
          AND p.archived = 0
          AND t.parent_gid IS NULL
        GROUP BY p.gid, p.name
        ORDER BY pendientes DESC
        """,
        params={"owner": owner_name}
    )


# =============================================================================
# QUERIES — FICHA PROVEEDOR
# =============================================================================

def get_projects_for_member(user_name: str):
    """Proyectos en los que participa un miembro/proveedor."""
    return query_to_df(
        """
        SELECT DISTINCT
            p.gid, p.name, p.owner_name, p.team_name,
            p.due_on, p.start_on, p.created_at, p.permalink_url,
            (SELECT COUNT(*) FROM task_projects tp
             JOIN tasks t ON tp.task_gid = t.gid
             WHERE tp.project_gid = p.gid AND t.parent_gid IS NULL
            ) AS total_tareas,
            (SELECT COUNT(*) FROM task_projects tp
             JOIN tasks t ON tp.task_gid = t.gid
             WHERE tp.project_gid = p.gid AND t.completed = 1 AND t.parent_gid IS NULL
            ) AS tareas_completadas
        FROM projects p
        JOIN project_memberships pm ON p.gid = pm.project_gid
        WHERE pm.user_name = :user_name
          AND p.archived = 0
        ORDER BY p.due_on IS NULL, p.due_on, p.name
        """,
        params={"user_name": user_name}
    )


def get_member_tasks_assigned(user_name: str):
    """Tareas asignadas directamente a un miembro/proveedor."""
    return query_to_df(
        """
        SELECT
            t.gid, t.name AS task_name, t.completed,
            t.due_on, t.created_at, t.permalink_url,
            p.name AS project_name, p.gid AS project_gid
        FROM tasks t
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        WHERE t.assignee_name = :user_name
          AND p.archived = 0
          AND t.parent_gid IS NULL
        ORDER BY t.completed, t.due_on IS NULL, t.due_on
        """,
        params={"user_name": user_name}
    )


def get_member_custom_field_budgets(user_name: str):
    """
    Valores de custom fields numéricos (posibles presupuestos)
    en tareas/proyectos donde participa el miembro.
    """
    return query_to_df(
        """
        SELECT
            p.name AS project_name,
            tcf.custom_field_name,
            tcf.display_value,
            tcf.number_value
        FROM task_custom_field_values tcf
        JOIN tasks t ON tcf.task_gid = t.gid
        JOIN task_projects tp ON t.gid = tp.task_gid
        JOIN projects p ON tp.project_gid = p.gid
        JOIN project_memberships pm ON p.gid = pm.project_gid
        WHERE pm.user_name = :user_name
          AND p.archived = 0
          AND tcf.number_value IS NOT NULL
        ORDER BY p.name, tcf.custom_field_name
        """,
        params={"user_name": user_name}
    )
