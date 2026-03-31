"""
Página: ESTADO DE LOS PROYECTOS
================================
Vista detallada de proyectos con búsqueda, filtros y drill-down a tareas.
Proyectos agrupados en contenedores de grid 3-columnas por categoría (primer
token del nombre), ordenados de mayor a menor número de proyectos.
"""

import re
import json
import urllib.parse

import dash
from dash import html, dcc, callback, Output, Input, State, no_update
import plotly.graph_objects as go
from datetime import date
from database import (
    get_all_projects,
    get_project_detail,
    get_project_sections,
    get_project_tasks,
    get_task_subtasks,
    get_task_custom_fields,
    get_project_members,
    get_owners_list,
    get_portfolios_list,
)

dash.register_page(__name__, path="/estado", name="Estado de los Proyectos")

# Paleta de colores suaves para los contenedores de grupo
_GROUP_COLORS = [
    "#eaf2fb", "#e8f8f0", "#fef9e7", "#fae5e5", "#ede7f6",
    "#e0f2f1", "#fff3e0", "#e8eaf6", "#fce4ec", "#e0f7fa",
    "#f1f8e9", "#fff8e1", "#f3e5f5", "#e1f5fe", "#efebe9",
    "#f9fbe7", "#e8f5e9", "#fffde7", "#fbe9e7", "#f0f4c3",
]

# Reglas de agrupación: (palabras clave a buscar en el nombre, nombre del grupo)
# Se evalúan en orden; la primera coincidencia gana.
_GROUP_RULES = [
    (["penafiel"],                                  "Penafiel FC"),
    (["match day", "macth day", "matchday"],        "Match Day"),
    (["tareas previamente asignadas"],              "Tareas Previamente Asignadas"),
    (["transformación digital", "transformacion digital"], "Transformación Digital"),
    (["museo"],                                     "Museo"),
    (["proyectos ", "proyecto ", "proyectos\n"],    "Proyectos"),
]


def _extract_group(name: str) -> str:
    """Extrae la categoría/grupo del nombre de un proyecto.

    1. Comprueba reglas explícitas de palabras clave.
    2. Si ninguna coincide, usa el nombre completo como grupo propio.
    """
    if not name:
        return "Otros"
    lower = name.lower().strip()
    for keywords, group_name in _GROUP_RULES:
        for kw in keywords:
            if kw in lower:
                return group_name
    return name.strip()


def _format_date(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _due_class(due_on):
    """Devuelve clase CSS según proximidad de la fecha de entrega."""
    if due_on is None:
        return "normal"
    try:
        today = date.today()
        if hasattr(due_on, 'date'):
            due_on = due_on.date()
        delta = (due_on - today).days
        if delta < 0:
            return "overdue"
        elif delta <= 7:
            return "upcoming"
        return "normal"
    except Exception:
        return "normal"


def _badge_for_row(row):
    """Devuelve (clase_css, texto) del badge según progreso del proyecto."""
    total = int(row.get("total_tareas", 0))
    completadas = int(row.get("tareas_completadas", 0))
    pct = (completadas / total * 100) if total > 0 else 0

    if total == 0:
        return "badge-gray", "Sin tareas"
    elif pct == 100:
        return "badge-green", "100%"
    elif pct >= 50:
        return "badge-blue", f"{pct:.0f}%"
    elif pct > 0:
        return "badge-orange", f"{pct:.0f}%"
    else:
        return "badge-red", "0%"


def _build_group_card(group_name, rows, bg_color):
    """Construye un contenedor de grupo con la lista compacta de proyectos."""
    items = []
    for _, row in rows.iterrows():
        badge_cls, badge_txt = _badge_for_row(row)
        items.append(
            html.Li(
                className="project-group-item",
                id={"type": "project-card", "index": row["gid"]},
                n_clicks=0,
                children=[
                    html.Span(row["name"], className="project-group-item-name"),
                    html.Span(badge_txt,
                              className=f"badge {badge_cls} project-group-item-badge"),
                ],
            )
        )

    return html.Div(className="project-group-card", style={"backgroundColor": bg_color}, children=[
        html.Div(className="project-group-header", children=[
            html.H4(group_name, className="project-group-title"),
            html.Span(f"{len(items)}", className="project-group-count"),
        ]),
        html.Ul(className="project-group-list", children=items),
    ])


def _build_task_item(row):
    """Construye un elemento de tarea."""
    check_cls = "task-check completed" if row.get("completed") else "task-check"
    name_cls = "task-name completed" if row.get("completed") else "task-name"
    due_cls = f"task-due {_due_class(row.get('due_on'))}"

    items = [
        html.Div(className=check_cls),
        html.Div(row.get("name", ""), className=name_cls),
    ]
    if row.get("assignee_name"):
        items.append(html.Div(row["assignee_name"], className="task-assignee"))
    items.append(html.Div(
        _format_date(row.get("due_on")),
        className=due_cls
    ))

    subtask_indicator = ""
    if row.get("num_subtasks", 0) > 0:
        subtask_indicator = html.Span(
            f"  ▸ {row['num_subtasks']} subtareas",
            style={"fontSize": "0.7rem", "color": "#999", "marginLeft": "8px"}
        )
        items.append(subtask_indicator)

    return html.Li(className="task-item", children=items)


def _build_subtask_item(row):
    """Construye un elemento de subtarea."""
    check_cls = "task-check completed" if row.get("completed") else "task-check"
    name_cls = "task-name completed" if row.get("completed") else "task-name"

    items = [
        html.Div(className=check_cls, style={"width": "14px", "height": "14px"}),
        html.Div(row.get("name", ""), className=name_cls),
    ]
    if row.get("assignee_name"):
        items.append(html.Div(row["assignee_name"], className="task-assignee"))
    if row.get("due_on"):
        items.append(html.Div(
            _format_date(row["due_on"]),
            className=f"task-due {_due_class(row.get('due_on'))}"
        ))

    return html.Li(className="subtask-item", children=items)


def _build_project_detail(project_gid):
    """Construye el panel de detalle completo de un proyecto."""
    try:
        df_proj = get_project_detail(project_gid)
        if df_proj.empty:
            return html.P("Proyecto no encontrado", style={"color": "#999"})
        proj = df_proj.iloc[0]
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": "#e74c3c"})

    # Cabecera del proyecto
    detail_meta = []
    for label, key in [
        ("Responsable", "owner_name"), ("Equipo", "team_name"),
        ("Fecha Inicio", "start_on"), ("Fecha Entrega", "due_on"),
        ("Creado", "created_at"), ("Modificado", "modified_at"),
    ]:
        val = proj.get(key)
        if val is not None:
            if "fecha" in label.lower() or "cread" in label.lower() or "modif" in label.lower():
                val = _format_date(val)
            detail_meta.append(
                html.Div(className="detail-meta-item", children=[
                    html.Strong(f"{label}: "), str(val)
                ])
            )

    # Miembros
    try:
        df_members = get_project_members(project_gid)
        members_section = html.Div(className="members-list", children=[
            html.Span(row["user_name"], className="member-chip")
            for _, row in df_members.iterrows()
            if row.get("user_name")
        ]) if not df_members.empty else html.P("Sin miembros",
                                                style={"color": "#999", "fontSize": "0.8rem"})
    except Exception:
        members_section = html.P("Error cargando miembros", style={"color": "#999"})

    # Notas
    notes = proj.get("notes", "")
    notes_section = html.P(
        notes if notes else "Sin descripción",
        style={"fontSize": "0.85rem", "color": "#555", "whiteSpace": "pre-wrap",
               "maxHeight": "120px", "overflow": "auto"}
    )

    # Tareas agrupadas por sección
    try:
        df_tasks = get_project_tasks(project_gid)
    except Exception:
        df_tasks = None

    # Construir contenido de tareas
    def _build_tasks_for_df(task_df, pending_only=False):
        content = []
        if task_df is not None and not task_df.empty:
            grouped = task_df.groupby(
                task_df["section_name"].fillna("Sin sección"), sort=False
            )
            for section_name, group in grouped:
                content.append(
                    html.Div(section_name, className="section-header-task")
                )
                task_items = []
                for _, task_row in group.iterrows():
                    task_items.append(_build_task_item(task_row))
                    if task_row.get("num_subtasks", 0) > 0:
                        try:
                            df_sub = get_task_subtasks(task_row["gid"])
                            if not df_sub.empty:
                                # Si modo pendientes, filtrar subtareas completadas
                                if pending_only:
                                    df_sub = df_sub[df_sub["completed"] == 0]
                                if not df_sub.empty:
                                    sub_items = [_build_subtask_item(r)
                                                 for _, r in df_sub.iterrows()]
                                    task_items.append(
                                        html.Ul(className="subtask-list",
                                                children=sub_items)
                                    )
                        except Exception:
                            pass
                content.append(
                    html.Ul(className="task-list", children=task_items)
                )
        else:
            content = [html.P("No hay tareas en este proyecto",
                              style={"color": "#999", "padding": "20px"})]
        return content

    tasks_all = _build_tasks_for_df(df_tasks)

    # Versión solo pendientes (tareas + subtareas pendientes)
    df_pending = None
    if df_tasks is not None and not df_tasks.empty:
        df_pending = df_tasks[df_tasks["completed"] == 0]
    tasks_pending = _build_tasks_for_df(df_pending, pending_only=True)

    # Estadísticas
    task_stats = None
    if df_tasks is not None and not df_tasks.empty:
        total_t = len(df_tasks)
        comp_t = int(df_tasks["completed"].sum())
        pend_t = total_t - comp_t
        pct_t = (comp_t / total_t * 100) if total_t > 0 else 0

        task_stats = html.Div(style={"marginBottom": "15px"}, children=[
            html.Div(className="progress-bar-bg", style={"height": "10px"}, children=[
                html.Div(className="progress-bar-fill",
                         style={"width": f"{pct_t:.0f}%", "height": "10px"}),
            ]),
            html.P(
                f"{comp_t} de {total_t} tareas completadas ({pct_t:.0f}%) · "
                f"{pend_t} pendientes",
                style={"fontSize": "0.8rem", "color": "#666", "marginTop": "5px"}
            ),
        ])

    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", children=[
            # Botón X para cerrar
            html.Button("✕", id="close-detail-btn", className="detail-close-btn", n_clicks=0),

            html.H3(proj.get("name", ""), className="detail-title"),
            html.Div(className="detail-meta", children=detail_meta),

            html.Div(style={"marginBottom": "15px"}, children=[
                html.Strong("Descripción", style={"fontSize": "0.85rem", "color": "#1a3a5c"}),
                notes_section,
            ]),

            html.Div(style={"marginBottom": "15px"}, children=[
                html.Strong("Miembros del Proyecto", style={"fontSize": "0.85rem", "color": "#1a3a5c"}),
                html.Div(members_section, style={"marginTop": "6px"}),
            ]),

            html.Hr(style={"margin": "15px 0", "border": "none", "borderTop": "1px solid #eee"}),

            html.Strong("Tareas", style={"fontSize": "0.95rem", "color": "#1a3a5c"}),
            task_stats,

            # Toggle: Mostrar solo pendientes
            html.Div(className="detail-toggle-bar", children=[
                html.Span("Mostrar tareas pendientes", className="detail-toggle-label"),
                html.Button(id="toggle-pending-btn", className="detail-toggle-switch",
                            n_clicks=0),
            ]),

            # Contenedor con ambas versiones (una visible, otra oculta)
            html.Div(id="tasks-all-container", children=tasks_all),
            html.Div(id="tasks-pending-container", children=tasks_pending,
                     style={"display": "none"}),

            html.Div(style={"marginTop": "15px", "textAlign": "right"}, children=[
                html.A(
                    "Abrir en Asana ↗",
                    href=proj.get("permalink_url", "#"),
                    target="_blank",
                    style={"fontSize": "0.8rem", "color": "#2c5282"}
                )
            ]) if proj.get("permalink_url") else None,
        ]),
    ])


# =============================================================================
# LAYOUT
# =============================================================================

def _build_toggle_buttons(values, btn_type):
    """Genera botones toggle para un grupo de filtros."""
    buttons = []
    for val in values:
        buttons.append(
            html.Button(
                val,
                id={"type": btn_type, "index": val},
                className="filter-toggle-btn",
                n_clicks=0,
            )
        )
    return buttons


def _build_filter_sections():
    """Construye las secciones de filtros con toggle buttons."""
    try:
        df_owners = get_owners_list()
        owner_vals = [v for v in df_owners["owner_name"].tolist() if v != "Sin asignar"]
    except Exception:
        owner_vals = []

    try:
        df_portfolios = get_portfolios_list()
        portfolio_vals = df_portfolios["portfolio_name"].tolist()
    except Exception:
        portfolio_vals = []

    sections = []

    # Búsqueda
    sections.append(
        html.Div(style={"marginBottom": "12px"}, children=[
            dcc.Input(
                id="search-project",
                type="text",
                placeholder="Buscar proyecto por nombre...",
                className="search-input",
                debounce=True,
                style={"maxWidth": "400px"},
            ),
        ])
    )

    # Responsable toggle buttons
    if owner_vals:
        sections.append(
            html.Div(className="filter-toggle-section", children=[
                html.Span("RESPONSABLE DEL PROYECTO", className="filter-toggle-label"),
                html.Div(
                    className="filter-toggle-group",
                    children=_build_toggle_buttons(owner_vals, "owner-btn"),
                ),
            ])
        )

    # Portafolio toggle buttons
    if portfolio_vals:
        sections.append(
            html.Div(className="filter-toggle-section", children=[
                html.Span("PORTAFOLIO", className="filter-toggle-label"),
                html.Div(
                    className="filter-toggle-group",
                    children=_build_toggle_buttons(portfolio_vals, "team-btn"),
                ),
            ])
        )

    return sections


layout = html.Div([
    # Stores para filtros activos (listas de valores seleccionados)
    dcc.Store(id="active-owners", data=[]),
    dcc.Store(id="active-teams", data=[]),  # now stores portfolio filter
    dcc.Store(id="selected-project-gid", data=None),

    # Filtros toggle
    html.Div(id="filter-sections", children=_build_filter_sections()),

    # Grid de proyectos agrupados
    html.Div(id="projects-list"),

    # Panel de detalle (overlay)
    html.Div(
        id="project-detail-panel",
        style={"marginTop": "20px"},
        children=[
            html.Button(id="close-detail-btn", style={"display": "none"}, n_clicks=0),
            html.Button(id="toggle-pending-btn", style={"display": "none"}, n_clicks=0),
            html.Div(id="tasks-all-container", style={"display": "none"}),
            html.Div(id="tasks-pending-container", style={"display": "none"}),
        ],
    ),
])


# =============================================================================
# CALLBACKS
# =============================================================================

@callback(
    Output("active-owners", "data"),
    Output({"type": "owner-btn", "index": dash.ALL}, "className"),
    Input({"type": "owner-btn", "index": dash.ALL}, "n_clicks"),
    State("active-owners", "data"),
    prevent_initial_call=True,
)
def toggle_owner_filter(n_clicks_list, active):
    """Toggle de filtros de responsable. Actualiza Store y clases CSS."""
    ctx = dash.callback_context
    if not ctx.triggered or not any(n_clicks_list):
        return no_update, no_update

    trigger_id = ctx.triggered[0]["prop_id"]
    try:
        parsed = json.loads(trigger_id.split(".")[0])
        clicked = parsed["index"]
    except Exception:
        return no_update, no_update

    active = list(active) if active else []
    if clicked in active:
        active.remove(clicked)
    else:
        active.append(clicked)

    # Reconstruir clases para todos los botones
    all_ids = ctx.inputs_list[0]
    classes = []
    for item in all_ids:
        val = item["id"]["index"]
        cls = "filter-toggle-btn active" if val in active else "filter-toggle-btn"
        classes.append(cls)

    return active, classes


@callback(
    Output("active-teams", "data"),
    Output({"type": "team-btn", "index": dash.ALL}, "className"),
    Input({"type": "team-btn", "index": dash.ALL}, "n_clicks"),
    State("active-teams", "data"),
    prevent_initial_call=True,
)
def toggle_team_filter(n_clicks_list, active):
    """Toggle de filtros de equipo. Actualiza Store y clases CSS."""
    ctx = dash.callback_context
    if not ctx.triggered or not any(n_clicks_list):
        return no_update, no_update

    trigger_id = ctx.triggered[0]["prop_id"]
    try:
        parsed = json.loads(trigger_id.split(".")[0])
        clicked = parsed["index"]
    except Exception:
        return no_update, no_update

    active = list(active) if active else []
    if clicked in active:
        active.remove(clicked)
    else:
        active.append(clicked)

    all_ids = ctx.inputs_list[0]
    classes = []
    for item in all_ids:
        val = item["id"]["index"]
        cls = "filter-toggle-btn active" if val in active else "filter-toggle-btn"
        classes.append(cls)

    return active, classes


@callback(
    Output("projects-list", "children"),
    Input("search-project", "value"),
    Input("active-owners", "data"),
    Input("active-teams", "data"),
    Input("session-store", "data"),
)
def update_projects_list(search, active_owners, active_teams, session):
    """Agrupa proyectos por categoría y muestra en grid 3-columnas."""
    try:
        df = get_all_projects()
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": "#e74c3c"})

    if df.empty:
        return html.P("No hay proyectos activos",
                       style={"color": "#999", "padding": "20px"})

    # Filtrar
    if search:
        df = df[df["name"].str.contains(search, case=False, na=False)]
    if active_owners:
        df = df[df["owner_name"].isin(active_owners)]
    if active_teams:
        df = df[df["portfolio_name"].isin(active_teams)]

    if df.empty:
        return html.P("No se encontraron proyectos con esos filtros",
                       style={"color": "#999", "padding": "20px"})

    # Agrupar por categoría extraída del nombre
    df["_group"] = df["name"].apply(_extract_group)

    # Ordenar grupos por cantidad de proyectos (mayor primero)
    group_counts = df.groupby("_group").size().sort_values(ascending=False)
    sorted_groups = group_counts.index.tolist()

    # Construir contenedores de grupo
    cards = []
    for i, group_name in enumerate(sorted_groups):
        group_df = df[df["_group"] == group_name]
        bg_color = _GROUP_COLORS[i % len(_GROUP_COLORS)]
        cards.append(_build_group_card(group_name, group_df, bg_color))

    return html.Div(className="projects-grid", children=cards)


@callback(
    Output("project-detail-panel", "children"),
    Input({"type": "project-card", "index": dash.ALL}, "n_clicks"),
    Input("close-detail-btn", "n_clicks"),
    Input("url", "search"),
    prevent_initial_call=True,
)
def show_project_detail(n_clicks_list, close_clicks, url_search):
    """Muestra o cierra el detalle del proyecto seleccionado."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    trigger_id = ctx.triggered[0]["prop_id"]

    # Cerrar panel — devolver placeholders ocultos
    if trigger_id == "close-detail-btn.n_clicks":
        return [
            html.Button(id="close-detail-btn", style={"display": "none"}, n_clicks=0),
            html.Button(id="toggle-pending-btn", style={"display": "none"}, n_clicks=0),
            html.Div(id="tasks-all-container", style={"display": "none"}),
            html.Div(id="tasks-pending-container", style={"display": "none"}),
        ]

    # Comprobar si viene por URL (?proyecto=gid)
    if trigger_id == "url.search" and url_search:
        params = urllib.parse.parse_qs(url_search.lstrip("?"))
        if "proyecto" in params:
            gid = params["proyecto"][0]
            return _build_project_detail(gid)

    # Comprobar si se hizo clic en alguna tarjeta / item del grid
    if "project-card" in trigger_id:
        # Verificar que fue un clic real (n_clicks > 0), no un re-render
        triggered_value = ctx.triggered[0].get("value")
        if not triggered_value or triggered_value == 0:
            return no_update
        try:
            parsed = json.loads(trigger_id.split(".")[0])
            gid = parsed["index"]
            return _build_project_detail(gid)
        except Exception:
            pass

    return no_update


@callback(
    Output("tasks-all-container", "style"),
    Output("tasks-pending-container", "style"),
    Output("toggle-pending-btn", "className"),
    Input("toggle-pending-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_pending_tasks(n_clicks):
    """Alterna entre mostrar todas las tareas o solo las pendientes."""
    if n_clicks and n_clicks % 2 == 1:
        # Activo: mostrar solo pendientes
        return (
            {"display": "none"},
            {"display": "block"},
            "detail-toggle-switch active",
        )
    # Inactivo: mostrar todas
    return (
        {"display": "block"},
        {"display": "none"},
        "detail-toggle-switch",
    )
