"""
Página: Proyectos por Mes
==========================
Muestra los proyectos con fecha de entrega en un mes concreto.
Se accede haciendo clic en un mes desde la Visión Global.
"""

import dash
from dash import html, dcc, callback, Output, Input
from database import get_projects_for_month

dash.register_page(
    __name__,
    path_template="/proyectos/<mes>",
    name="Proyectos por Mes",
)

MESES_ES = {
    "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
    "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
    "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
}


def _format_month(mes_str):
    if mes_str == "sin_fecha":
        return "Sin Fecha de Entrega"
    try:
        year, month = mes_str.split("-")
        return f"{MESES_ES.get(month, month)} {year}"
    except Exception:
        return mes_str


def _format_date(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _build_project_card(row):
    """Construye una tarjeta de proyecto individual."""
    total = int(row.get("tareas_pendientes", 0)) + int(row.get("tareas_completadas", 0))
    completadas = int(row.get("tareas_completadas", 0))
    pendientes = int(row.get("tareas_pendientes", 0))
    pct = (completadas / total * 100) if total > 0 else 0

    meta_items = []
    if row.get("owner_name"):
        meta_items.append(html.Span(["👤 ", row["owner_name"]]))
    if row.get("team_name"):
        meta_items.append(html.Span(["🏠 ", row["team_name"]]))
    if row.get("due_on"):
        meta_items.append(html.Span(["📅 Entrega: ", _format_date(row["due_on"])]))
    if row.get("start_on"):
        meta_items.append(html.Span(["🚀 Inicio: ", _format_date(row["start_on"])]))

    notes_preview = ""
    if row.get("notes"):
        notes_preview = str(row["notes"])[:200]
        if len(str(row["notes"])) > 200:
            notes_preview += "..."

    return dcc.Link(
        href=f"/estado?proyecto={row['gid']}",
        style={"textDecoration": "none", "color": "inherit"},
        children=[
            html.Div(className="project-card", children=[
                html.Div(className="project-card-header", children=[
                    html.H4(row["name"], className="project-card-name"),
                    html.Span(
                        f"{completadas}/{total} tareas",
                        className="badge badge-blue"
                    ),
                ]),
                html.Div(className="project-card-meta", children=meta_items),
                html.Div(className="project-card-progress", children=[
                    html.Div(className="progress-bar-bg", children=[
                        html.Div(className="progress-bar-fill",
                                 style={"width": f"{pct:.0f}%"}),
                    ]),
                    html.Div(
                        f"{pct:.0f}% completado · {pendientes} pendientes",
                        className="progress-text"
                    ),
                ]),
                html.P(notes_preview,
                       style={"fontSize": "0.78rem", "color": "#888",
                              "marginTop": "8px"}) if notes_preview else None,
            ])
        ]
    )


def layout(mes=None, **kwargs):
    """Layout dinámico según el mes seleccionado."""
    if mes is None:
        mes = "sin_fecha"

    label = _format_month(mes)

    try:
        df = get_projects_for_month(mes)
    except Exception as e:
        return html.Div([
            dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),
            html.P(f"Error cargando proyectos: {e}",
                   style={"color": "#e74c3c"}),
        ])

    # Botón de volver
    header = html.Div([
        dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),
        html.H2(f"Proyectos — {label}", className="page-title"),
        html.P(f"{len(df)} proyecto{'s' if len(df) != 1 else ''} encontrado{'s' if len(df) != 1 else ''}",
               className="page-subtitle"),
    ])

    if df.empty:
        return html.Div([
            header,
            html.Div(className="section-container", children=[
                html.P("No hay proyectos para este período",
                       style={"color": "#999", "textAlign": "center", "padding": "40px"}),
            ]),
        ])

    # Generar tarjetas de proyectos
    project_cards = []
    for _, row in df.iterrows():
        project_cards.append(_build_project_card(row))

    return html.Div([
        header,
        html.Div(children=project_cards),
    ])
