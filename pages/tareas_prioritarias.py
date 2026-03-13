"""
Página: TAREAS PRIORITARIAS
=============================
Grid de 3 columnas: Tardías | Esta semana | Siguiente semana.
Filtros toggle de Responsable y Equipo (multi-select).
"""

import json

import dash
from dash import html, dcc, callback, Output, Input, State, no_update
from datetime import date
from database import get_priority_tasks

dash.register_page(__name__, path="/tareas-prioritarias", name="Tareas Prioritarias")


def _format_date(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _days_label(due_on):
    """Devuelve texto con los días de retraso o restantes."""
    if due_on is None:
        return ""
    try:
        today = date.today()
        if hasattr(due_on, "date"):
            due_on = due_on.date()
        delta = (due_on - today).days
        if delta < 0:
            return f"{abs(delta)}d retraso"
        elif delta == 0:
            return "Hoy"
        elif delta == 1:
            return "Mañana"
        else:
            return f"En {delta}d"
    except Exception:
        return ""


def _build_task_row(row):
    """Construye una fila de tarea dentro de una columna."""
    due_text = _format_date(row.get("due_on"))
    days_text = _days_label(row.get("due_on"))
    bucket = row.get("priority_bucket", "")

    if bucket == "overdue":
        days_color = "#e74c3c"
    elif bucket == "this_week":
        days_color = "#f39c12"
    else:
        days_color = "#2ecc71"

    assignee = row.get("assignee_name") or "Sin asignar"
    project = row.get("project_name") or ""

    return html.Div(
        className="priority-task-row",
        children=[
            html.Div(className="priority-task-urgency",
                      style={"backgroundColor": days_color}),
            html.Div(className="priority-task-info", children=[
                html.Div(row.get("task_name", ""), className="priority-task-name"),
                html.Div(className="priority-task-meta", children=[
                    html.Span(f"📁 {project}"),
                    html.Span(f"👤 {assignee}"),
                ]),
            ]),
            html.Div(className="priority-task-date", children=[
                html.Div(due_text, style={"fontSize": "0.78rem", "fontWeight": "600"}),
                html.Div(days_text, style={
                    "fontSize": "0.68rem", "color": days_color, "fontWeight": "600"
                }),
            ]),
            html.A(
                "↗", href=row.get("permalink_url", "#"), target="_blank",
                className="priority-task-link",
            ) if row.get("permalink_url") else None,
        ],
    )


def _build_column(title, color, tasks_df, empty_msg):
    """Construye una columna del grid (tardías / esta semana / siguiente)."""
    count = len(tasks_df)

    if tasks_df.empty:
        content = html.P(empty_msg, style={
            "color": "#999", "fontSize": "0.82rem", "padding": "20px 0",
            "textAlign": "center",
        })
    else:
        rows = [_build_task_row(row) for _, row in tasks_df.iterrows()]
        content = html.Div(children=rows)

    return html.Div(className="priority-column", children=[
        html.Div(className="priority-column-header",
                  style={"borderTopColor": color}, children=[
            html.H3(title, className="priority-column-title"),
            html.Span(f"{count}", className="priority-section-count",
                       style={"backgroundColor": color}),
        ]),
        html.Div(className="priority-column-body", children=[content]),
    ])


def _build_toggle_buttons(values, btn_type):
    """Genera botones toggle para filtros."""
    return [
        html.Button(
            val, id={"type": btn_type, "index": val},
            className="filter-toggle-btn", n_clicks=0,
        )
        for val in values
    ]


def _build_filters():
    """Construye los filtros de Responsable (asignado de tarea) y Equipo."""
    try:
        df = get_priority_tasks()
        # Responsable = assignee de la tarea (no owner del proyecto)
        assignees = sorted(
            df["assignee_name"].dropna().unique().tolist()
        ) if not df.empty else []
        # Equipos desde las tareas prioritarias
        teams = sorted(
            df["team_name"].dropna().unique().tolist()
        ) if not df.empty else []
    except Exception:
        assignees = []
        teams = []

    sections = []
    if assignees:
        sections.append(html.Div(className="filter-toggle-section", children=[
            html.Span("Responsable de tarea", className="filter-toggle-label"),
            html.Div(className="filter-toggle-group",
                      children=_build_toggle_buttons(assignees, "prio-owner-btn")),
        ]))
    if teams:
        sections.append(html.Div(className="filter-toggle-section", children=[
            html.Span("Equipo", className="filter-toggle-label"),
            html.Div(className="filter-toggle-group",
                      children=_build_toggle_buttons(teams, "prio-team-btn")),
        ]))
    return sections


# =============================================================================
# LAYOUT
# =============================================================================

layout = html.Div([
    dcc.Store(id="prio-active-owners", data=[]),
    dcc.Store(id="prio-active-teams", data=[]),

    # Filtros toggle
    html.Div(id="prio-filters", children=_build_filters()),

    # Grid 3 columnas
    html.Div(id="priority-grid"),
])


# =============================================================================
# CALLBACKS
# =============================================================================

@callback(
    Output("prio-active-owners", "data"),
    Output({"type": "prio-owner-btn", "index": dash.ALL}, "className"),
    Input({"type": "prio-owner-btn", "index": dash.ALL}, "n_clicks"),
    State("prio-active-owners", "data"),
    prevent_initial_call=True,
)
def toggle_prio_owner(n_clicks_list, active):
    ctx = dash.callback_context
    if not ctx.triggered or not any(n_clicks_list):
        raise dash.exceptions.PreventUpdate
    try:
        parsed = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
        clicked = parsed["index"]
    except Exception:
        raise dash.exceptions.PreventUpdate

    active = list(active) if active else []
    if clicked in active:
        active.remove(clicked)
    else:
        active.append(clicked)

    classes = [
        "filter-toggle-btn active" if item["id"]["index"] in active else "filter-toggle-btn"
        for item in ctx.inputs_list[0]
    ]
    return active, classes


@callback(
    Output("prio-active-teams", "data"),
    Output({"type": "prio-team-btn", "index": dash.ALL}, "className"),
    Input({"type": "prio-team-btn", "index": dash.ALL}, "n_clicks"),
    State("prio-active-teams", "data"),
    prevent_initial_call=True,
)
def toggle_prio_team(n_clicks_list, active):
    ctx = dash.callback_context
    if not ctx.triggered or not any(n_clicks_list):
        raise dash.exceptions.PreventUpdate
    try:
        parsed = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
        clicked = parsed["index"]
    except Exception:
        raise dash.exceptions.PreventUpdate

    active = list(active) if active else []
    if clicked in active:
        active.remove(clicked)
    else:
        active.append(clicked)

    classes = [
        "filter-toggle-btn active" if item["id"]["index"] in active else "filter-toggle-btn"
        for item in ctx.inputs_list[0]
    ]
    return active, classes


@callback(
    Output("priority-grid", "children"),
    Input("prio-active-owners", "data"),
    Input("prio-active-teams", "data"),
    Input("session-store", "data"),
)
def render_priority_grid(active_owners, active_teams, session):
    """Renderiza el grid 3-columnas con filtros aplicados."""
    try:
        df = get_priority_tasks()
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": "#e74c3c"})

    if df.empty:
        return html.P("No hay tareas prioritarias", style={"color": "#999", "padding": "20px"})

    # Aplicar filtros toggle
    # Responsable = assignee_name de la tarea (no owner_name del proyecto)
    if active_owners:
        df = df[df["assignee_name"].isin(active_owners)]
    if active_teams:
        df = df[df["team_name"].isin(active_teams)]

    # Separar en buckets
    df_overdue = df[df["priority_bucket"] == "overdue"].copy()
    df_this_week = df[df["priority_bucket"] == "this_week"].copy()
    df_next_week = df[df["priority_bucket"] == "next_week"].copy()

    # Tardías: ordenar de más reciente a más antigua (DESC)
    if not df_overdue.empty:
        df_overdue = df_overdue.sort_values("due_on", ascending=False)

    return html.Div(className="priority-grid-3col", children=[
        _build_column("Tareas Tardías", "#e74c3c",
                       df_overdue, "No hay tareas tardías"),
        _build_column("Esta Semana", "#f39c12",
                       df_this_week, "No hay tareas para esta semana"),
        _build_column("Siguiente Semana", "#2ecc71",
                       df_next_week, "No hay tareas para la siguiente semana"),
    ])
