"""
Página: FICHA DE RESPONSABLE
==============================
Vista detallada de un responsable (owner) con:
- Proyectos segmentados por deadline (entregado, corto, medio, largo plazo)
- Insights y gráficas de estado de tareas
- Tareas delegadas a otros pendientes de completar
"""

import json

import dash
from dash import html, dcc, callback, Output, Input, State, no_update, MATCH, ALL
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import urllib.parse
from datetime import date, timedelta
from database import (
    get_projects_for_owner,
    get_owner_pending_tasks,
    get_owner_delegated_pending,
    get_owner_tasks_by_status,
    get_delegated_tasks_detail,
    query_to_df,
)
from pages.selector_responsable import _get_image_path
from pages.estado import _build_project_detail

dash.register_page(
    __name__,
    path_template="/ficha-responsable/<owner_name>",
    name="Ficha Responsable",
)


def _format_date(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _abbreviate_name(name):
    """Abbreviate: 'Juan García Collazo' -> 'J. García'. Emails unchanged."""
    if not name or "@" in name:
        return name
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {parts[1]}"
    return name


def _classify_project(due_on):
    """
    Clasifica un proyecto según su fecha de entrega:
      - 'entregado' (due_on pasado y ya entregado) → verde
      - 'corto'     (≤30 días)                     → rojo
      - 'medio'     (31-60 días)                   → naranja
      - 'largo'     (>60 días)                      → gris
      - 'sin_fecha' (sin due_on)                    → gris claro
    """
    if due_on is None:
        return "sin_fecha"
    try:
        today = date.today()
        if hasattr(due_on, "date"):
            due_on = due_on.date()
        delta = (due_on - today).days
        if delta < 0:
            return "entregado"
        elif delta <= 30:
            return "corto"
        elif delta <= 60:
            return "medio"
        else:
            return "largo"
    except Exception:
        return "sin_fecha"


DEADLINE_CONFIG = {
    "entregado": {"color": "#2ecc71", "label": "Entregados / Vencidos",  "icon": "✅"},
    "corto":     {"color": "#e74c3c", "label": "Corto Plazo (≤30 días)", "icon": "🔴"},
    "medio":     {"color": "#f39c12", "label": "Medio Plazo (31-60 días)", "icon": "🟠"},
    "largo":     {"color": "#95a5a6", "label": "Largo Plazo (>60 días)",  "icon": "⬜"},
    "sin_fecha": {"color": "#bdc3c7", "label": "Sin Fecha de Entrega",   "icon": "❓"},
}


def _build_project_card(row, category):
    """Tarjeta de proyecto con color de borde según categoría."""
    cfg = DEADLINE_CONFIG.get(category, DEADLINE_CONFIG["sin_fecha"])
    total = int(row.get("total_tareas", 0))
    comp = int(row.get("tareas_completadas", 0))
    pend = int(row.get("tareas_pendientes", 0))
    pct = (comp / total * 100) if total > 0 else 0

    meta = []
    if row.get("team_name"):
        meta.append(html.Span(["🏠 ", str(row["team_name"])]))
    if row.get("due_on"):
        meta.append(html.Span(["📅 ", _format_date(row["due_on"])]))

    return html.Div(
        className="project-card",
        style={"borderLeftColor": cfg["color"]},
        children=[
            html.Div(className="project-card-header", children=[
                html.H4(row["name"], className="project-card-name"),
                html.Span(f"{comp}/{total}", className="badge badge-blue"),
            ]),
            html.Div(className="project-card-meta", children=meta),
            html.Div(className="project-card-progress", children=[
                html.Div(className="progress-bar-bg", children=[
                    html.Div(className="progress-bar-fill",
                             style={"width": f"{pct:.0f}%"}),
                ]),
                html.Div(f"{pct:.0f}% completado · {pend} pendientes",
                         className="progress-text"),
            ]),
        ]
    )


def _build_deadline_section(df, category):
    """Construye una sección de proyectos para una categoría de deadline."""
    cfg = DEADLINE_CONFIG[category]
    if df.empty:
        return None

    cards = [_build_project_card(row, category) for _, row in df.iterrows()]

    return html.Div(style={"marginBottom": "20px"}, children=[
        html.Div(
            style={
                "display": "flex", "alignItems": "center", "gap": "8px",
                "marginBottom": "10px", "padding": "8px 12px",
                "background": cfg["color"] + "18", "borderRadius": "6px",
                "borderLeft": f"4px solid {cfg['color']}",
            },
            children=[
                html.Span(cfg["icon"], style={"fontSize": "1.1rem"}),
                html.Strong(
                    f"{cfg['label']} ({len(df)})",
                    style={"color": cfg["color"], "fontSize": "0.9rem"}
                ),
            ]
        ),
        html.Div(children=cards),
    ])


def _build_task_status_pies(owner_name):
    """Grid de mini pie charts clickables: click verde=completadas, rojo=pendientes."""
    try:
        df = get_owner_tasks_by_status(owner_name)
        if df.empty:
            return html.P("Sin datos de tareas", style={"color": "#999"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    n_projects = len(df)
    pie_sz = max(60, min(95, 950 // max(n_projects, 1)))
    font_sz = max(9, min(14, pie_sz // 7))

    pie_cards = []
    project_names = []
    for i, (_, row) in enumerate(df.iterrows()):
        comp = int(row["completadas"])
        pend = int(row["pendientes"])
        total = comp + pend
        pct = (comp / total * 100) if total > 0 else 0
        pname = row["project_name"]
        project_names.append(pname)

        fig = go.Figure(data=[go.Pie(
            values=[comp, pend], labels=["Completadas", "Pendientes"],
            marker=dict(colors=["#2ecc71", "#e74c3c"]),
            hole=0.5, textinfo="none",
            hovertemplate="<b>%{label}</b><extra></extra>",
            customdata=[pname, pname],
        )])
        fig.update_layout(
            margin=dict(t=2, b=2, l=2, r=2), height=pie_sz, width=pie_sz,
            showlegend=False,
            annotations=[dict(text=f"<b>{pct:.0f}%</b>", x=0.5, y=0.5,
                              font_size=font_sz, font_family="Montserrat",
                              showarrow=False, font_color="#333")],
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )

        pie_cards.append(
            html.Div(style={"textAlign": "center", "flex": "1 1 0",
                             "minWidth": "0"}, children=[
                dcc.Graph(id={"type": "pie-project", "index": i},
                          figure=fig, config={"displayModeBar": False},
                          style={"height": f"{pie_sz}px", "width": f"{pie_sz}px",
                                 "margin": "0 auto", "cursor": "pointer"}),
                html.Div(pname,
                         style={"fontSize": "0.7rem", "fontWeight": "700",
                                "color": "#333", "marginTop": "3px",
                                "lineHeight": "1.15", "wordBreak": "break-word",
                                "overflow": "hidden",
                                "display": "-webkit-box",
                                "WebkitLineClamp": "2",
                                "WebkitBoxOrient": "vertical"}),
                html.Div(f"{comp}/{total}",
                         style={"fontSize": "0.65rem", "color": "#666",
                                "fontWeight": "600"}),
            ])
        )

    return html.Div(children=[
        dcc.Store(id="pie-project-names", data=project_names),
        html.Div(style={"display": "flex", "flexWrap": "nowrap", "gap": "4px",
                         "justifyContent": "space-between",
                         "width": "100%", "padding": "5px 0"},
                 children=pie_cards),
    ])


def _build_delegated_chart(owner_name):
    """Gráfico barras: tareas delegadas pendientes por persona."""
    try:
        df = get_owner_delegated_pending(owner_name)
        if df.empty:
            return html.P("No hay tareas delegadas pendientes",
                          style={"color": "#999", "fontSize": "0.85rem"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    names = df["assignee_name"].tolist()
    short = [_abbreviate_name(n) for n in names]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=short,
        y=df["tareas_pendientes"],
        marker_color="#e67e22",
        text=df["tareas_pendientes"],
        textposition="outside",
        textfont=dict(color="#333", size=10, family="Montserrat", weight="bold"),
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            "Tareas pendientes: %{y}<br>"
            "Deadline más cercano: %{text}<extra></extra>"
        ),
        customdata=names,
    ))

    max_y = df["tareas_pendientes"].max() * 1.3 if not df.empty else 1
    n_bars = len(df)
    # Dynamic height: min 200 for few bars, more for many
    chart_h = max(200, min(400, 120 + n_bars * 25))
    fig.update_layout(
        margin=dict(b=80, t=10, l=20, r=20),
        height=chart_h,
        xaxis=dict(tickfont=dict(size=9, family="Montserrat", weight="bold"),
                   tickangle=-30),
        yaxis=dict(showticklabels=False, range=[0, max_y]),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    return dcc.Graph(id="chart-delegated", figure=fig, config={"displayModeBar": False})


def _build_deadline_sections(classified):
    """Construye el contenedor con todas las secciones de deadline."""
    import pandas as pd
    if not any(classified.values()):
        return None

    sections = []
    for cat in ["corto", "medio", "largo", "entregado"]:
        df_cat = pd.DataFrame(classified[cat]) if classified[cat] else pd.DataFrame()
        section = _build_deadline_section(df_cat, cat)
        if section is not None:
            sections.append(section)

    if not sections:
        return None

    return html.Div(className="section-container", children=[
        html.Div(style={"maxHeight": "400px", "overflowY": "auto"}, children=sections),
    ])


def _build_urgent_tasks_table(owner_name):
    """Tabla con las tareas pendientes más urgentes."""
    try:
        df = get_owner_pending_tasks(owner_name)
        if df.empty:
            return html.P("No hay tareas pendientes 🎉",
                          style={"color": "#2ecc71", "fontWeight": "600"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    # Ordenar: más recientemente vencidas primero (DESC por due_on)
    df = df.sort_values("due_on", ascending=False, na_position="last")
    df_top = df.head(15)
    today = date.today()

    rows = []
    for _, t in df_top.iterrows():
        due = t.get("due_on")
        if due is not None:
            try:
                d = due.date() if hasattr(due, "date") else due
                delta = (d - today).days
                if delta < 0:
                    due_cls, due_txt = "task-due overdue", f"Vencida ({abs(delta)}d)"
                elif delta <= 7:
                    due_cls, due_txt = "task-due upcoming", f"{delta}d"
                else:
                    due_cls, due_txt = "task-due normal", _format_date(due)
            except Exception:
                due_cls, due_txt = "task-due normal", _format_date(due)
        else:
            due_cls, due_txt = "task-due normal", "—"

        rows.append(html.Li(className="task-item", children=[
            html.Div(className="task-check"),
            html.Div(children=[
                html.Div(t.get("task_name", ""), className="task-name"),
                html.Div(t.get("project_name", ""),
                         style={"fontSize": "0.7rem", "color": "#999"}),
            ], style={"flex": "1"}),
            html.Div(t.get("assignee_name", "Sin asignar"),
                     className="task-assignee"),
            html.Div(due_txt, className=due_cls),
        ]))

    remaining = len(df) - len(df_top)
    if remaining > 0:
        rows.append(html.Li(
            style={"padding": "10px", "textAlign": "center",
                   "color": "#999", "fontSize": "0.8rem"},
            children=f"... y {remaining} tareas más"
        ))

    return html.Ul(className="task-list", children=rows)


# =============================================================================
# LAYOUT
# =============================================================================

def layout(owner_name=None, **kwargs):
    if not owner_name:
        return html.Div([
            dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),
            html.P("No se especificó un responsable", style={"color": "#999"}),
        ])

    owner_name = urllib.parse.unquote(owner_name)

    # Obtener proyectos
    try:
        df_projects = get_projects_for_owner(owner_name)
    except Exception as e:
        return html.Div([
            dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),
            html.P(f"Error: {e}", style={"color": "#e74c3c"}),
        ])

    # Clasificar proyectos por deadline
    classified = {"entregado": [], "corto": [], "medio": [], "largo": [], "sin_fecha": []}
    for _, row in df_projects.iterrows():
        cat = _classify_project(row.get("due_on"))
        classified[cat].append(row)

    # KPIs del responsable
    total_proj = len(df_projects)
    total_tareas = int(df_projects["total_tareas"].sum()) if not df_projects.empty else 0
    total_pend = int(df_projects["tareas_pendientes"].sum()) if not df_projects.empty else 0
    total_comp = int(df_projects["tareas_completadas"].sum()) if not df_projects.empty else 0
    pct_global = (total_comp / total_tareas * 100) if total_tareas > 0 else 0

    img_src = _get_image_path(owner_name)

    return html.Div([
        dcc.Link("← Volver", href="/fichas-responsables", className="back-btn"),

        # Header: nombre + imagen a la derecha (tamaño banner)
        html.Div(style={"display": "flex", "justifyContent": "flex-end",
                         "alignItems": "center", "marginBottom": "8px"}, children=[
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "15px"}, children=[
                html.Div(owner_name, style={"fontSize": "1.8rem", "fontWeight": "600",
                                             "color": "var(--white)"}),
                html.Img(src=img_src, className="responsable-img",
                         style={"width": "60px", "height": "60px"}),
            ]),
        ]),

        # KPIs (clickable)
        html.Div(className="kpis-container", style={"marginBottom": "8px"}, children=[
            html.Div(className="kpis-row", children=[
                html.Div(id="kpi-proyectos", className="kpi-card",
                         style={"cursor": "pointer"}, n_clicks=0, children=[
                    html.Div(str(total_proj), className="kpi-value"),
                    html.Div("PROYECTOS", className="kpi-label"),
                ]),
                html.Div(id="kpi-tareas-totales", className="kpi-card",
                         style={"cursor": "pointer"}, n_clicks=0, children=[
                    html.Div(str(total_tareas), className="kpi-value"),
                    html.Div("TAREAS TOTALES", className="kpi-label"),
                ]),
                html.Div(id="kpi-tareas-pendientes", className="kpi-card",
                         style={"cursor": "pointer"}, n_clicks=0, children=[
                    html.Div(str(total_pend), className="kpi-value",
                             style={"color": "#e74c3c"}),
                    html.Div("TAREAS PENDIENTES", className="kpi-label"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div(f"{pct_global:.0f}%", className="kpi-value",
                             style={"color": "#2ecc71"}),
                    html.Div("COMPLETADO", className="kpi-label"),
                ]),
            ]),
        ]),

        # Gráficos insights
        html.Div(className="graphs-container", children=[
            # Estado de tareas por proyecto (pie charts)
            html.Div(className="graphs-row", children=[
                html.Div(className="graph-card full-width", style={"background": "var(--white)",
                         "borderRadius": "8px", "padding": "12px"}, children=[
                    html.H4("Estado de Tareas por Proyecto",
                             style={"color": "var(--primary-blue)", "marginBottom": "8px"}),
                    _build_task_status_pies(owner_name),
                ]),
            ]),

            # Tareas delegadas pendientes (clickable)
            html.Div(className="graphs-row", children=[
                html.Div(className="graph-card full-width", style={"background": "var(--white)",
                         "borderRadius": "8px", "padding": "12px"}, children=[
                    html.H4("Tareas Delegadas Pendientes de Completar",
                             style={"color": "var(--primary-blue)", "marginBottom": "5px"}),
                    html.P("Haz clic en una barra para ver el detalle",
                           style={"fontSize": "0.75rem", "color": "#999",
                                  "textAlign": "center", "margin": "0 0 5px 0"}),
                    _build_delegated_chart(owner_name),
                ]),
            ]),
        ]),

        # Proyectos segmentados por deadline
        _build_deadline_sections(classified),

        # Stores y paneles para callbacks
        dcc.Store(id="ficha-owner-name", data=owner_name),
        html.Div(id="delegated-detail-panel", children=[
            html.Button(id="close-delegated-detail", style={"display": "none"}, n_clicks=0),
        ]),
        html.Div(id="kpi-detail-panel", children=[
            html.Button(id="close-kpi-detail", style={"display": "none"}, n_clicks=0),
        ]),
        html.Div(id="pie-detail-panel", children=[
            html.Button(id="close-pie-detail", style={"display": "none"}, n_clicks=0),
        ]),
        html.Div(id="ficha-project-detail-panel", children=[
            html.Button(id="close-ficha-project-detail", style={"display": "none"}, n_clicks=0),
        ]),
    ])


# =============================================================================
# CALLBACKS
# =============================================================================

@callback(
    Output("delegated-detail-panel", "children"),
    Input("chart-delegated", "clickData"),
    Input("close-delegated-detail", "n_clicks"),
    Input("ficha-owner-name", "data"),
    prevent_initial_call=True,
)
def show_delegated_detail(click_data, close_clicks, owner_name):
    """Al clickar en una barra del gráfico de delegadas, muestra detalle. X cierra."""
    ctx = dash.callback_context
    if ctx.triggered and ctx.triggered[0]["prop_id"] == "close-delegated-detail.n_clicks":
        return [html.Button(id="close-delegated-detail", style={"display": "none"}, n_clicks=0)]

    if not click_data or not click_data.get("points") or not owner_name:
        return no_update

    assignee = click_data["points"][0].get("customdata", "") or click_data["points"][0].get("x", "")
    if not assignee:
        return no_update

    try:
        df = get_delegated_tasks_detail(owner_name, assignee)
        if df.empty:
            return None
    except Exception:
        return None

    rows = []
    for _, r in df.iterrows():
        due = r.get("due_on")
        due_text = _format_date(due) if due else "Sin fecha"
        rows.append(html.Div(className="priority-task-row", children=[
            html.Div(className="priority-task-urgency",
                      style={"backgroundColor": "#e67e22"}),
            html.Div(className="priority-task-info", children=[
                html.Div(r["task_name"], className="priority-task-name"),
                html.Div(className="priority-task-meta", children=[
                    html.Span(f"📁 {r.get('project_name', '')}"),
                ]),
            ]),
            html.Div(className="priority-task-date", children=[
                html.Div(due_text, style={"fontSize": "0.8rem", "fontWeight": "600"}),
            ]),
            html.A(
                "↗", href=r.get("permalink_url", "#"), target="_blank",
                className="priority-task-link",
            ) if r.get("permalink_url") else None,
        ]))

    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", style={"maxWidth": "700px"}, children=[
            html.Button("✕", id="close-delegated-detail",
                         className="detail-close-btn", n_clicks=0),
            html.H3(f"Tareas delegadas a: {assignee}", className="detail-title"),
            html.P(f"{len(df)} tareas pendientes en proyectos de {owner_name}",
                   style={"fontSize": "0.85rem", "color": "#e67e22",
                          "fontWeight": "600", "marginBottom": "12px"}),
            html.Div(children=rows),
        ]),
    ])


# =============================================================================
# CALLBACK — KPI DETAIL PANELS
# =============================================================================

@callback(
    Output("kpi-detail-panel", "children"),
    Input("kpi-proyectos", "n_clicks"),
    Input("kpi-tareas-totales", "n_clicks"),
    Input("kpi-tareas-pendientes", "n_clicks"),
    Input("close-kpi-detail", "n_clicks"),
    Input("ficha-owner-name", "data"),
    prevent_initial_call=True,
)
def show_kpi_detail(n_proj, n_total, n_pend, n_close, owner_name):
    """Muestra detalle al clickar en una KPI card."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    trigger = ctx.triggered[0]["prop_id"]

    if trigger == "close-kpi-detail.n_clicks":
        return [html.Button(id="close-kpi-detail", style={"display": "none"}, n_clicks=0)]

    if not owner_name:
        return no_update

    # --- PROYECTOS ---
    if trigger == "kpi-proyectos.n_clicks" and n_proj:
        try:
            df = get_projects_for_owner(owner_name)
            if df.empty:
                return no_update
        except Exception:
            return no_update

        # Sort by % completion ascending (least complete first)
        df = df.copy()
        df["_pct"] = df.apply(
            lambda r: (int(r["tareas_completadas"]) / int(r["total_tareas"]) * 100)
            if int(r["total_tareas"]) > 0 else 0, axis=1)
        df = df.sort_values("_pct", ascending=True)

        rows = []
        for _, r in df.iterrows():
            total_t = int(r.get("total_tareas", 0))
            pend_t = int(r.get("tareas_pendientes", 0))
            comp_t = int(r.get("tareas_completadas", 0))
            pct = r["_pct"]
            due = _format_date(r.get("due_on"))
            proj_gid = str(r.get("gid", ""))

            rows.append(html.Div(
                id={"type": "kpi-project-row", "index": proj_gid},
                className="priority-task-row",
                style={"cursor": "pointer"}, n_clicks=0,
                children=[
                    html.Div(className="priority-task-urgency",
                              style={"backgroundColor": "#2c5282"}),
                    html.Div(className="priority-task-info", children=[
                        html.Div(r.get("name", ""), className="priority-task-name"),
                        html.Div(className="priority-task-meta", children=[
                            html.Span(f"📋 {total_t} tareas ({comp_t} completadas, {pend_t} pendientes)"),
                            html.Span(f"📅 Entrega: {due}"),
                        ]),
                    ]),
                    html.Div(className="priority-task-date", children=[
                        html.Div(f"{pct:.0f}%", style={"fontSize": "0.85rem",
                                 "fontWeight": "700",
                                 "color": "#2ecc71" if pct >= 50 else "#e74c3c"}),
                    ]),
                ],
            ))

        return _kpi_overlay("Proyectos", f"{len(df)} proyectos (ordenados por % completado)", "#2c5282", rows)

    # --- TAREAS TOTALES ---
    if trigger == "kpi-tareas-totales.n_clicks" and n_total:
        try:
            df = query_to_df("""
                SELECT t.name AS task_name, t.assignee_name, t.due_on,
                       t.completed, t.permalink_url,
                       p.name AS project_name
                FROM tasks t
                JOIN task_projects tp ON t.gid = tp.task_gid
                JOIN projects p ON tp.project_gid = p.gid
                WHERE p.owner_name = :owner AND p.archived = 0
                  AND t.parent_gid IS NULL
                ORDER BY t.completed, t.due_on IS NULL, t.due_on
            """, params={"owner": owner_name})
            if df.empty:
                return no_update
        except Exception:
            return no_update

        rows = _build_task_rows(df)
        return _kpi_overlay("Tareas Totales", f"{len(df)} tareas en sus proyectos", "#1a3a5c", rows)

    # --- TAREAS PENDIENTES ---
    if trigger == "kpi-tareas-pendientes.n_clicks" and n_pend:
        try:
            df = get_owner_pending_tasks(owner_name)
            if df.empty:
                return no_update
        except Exception:
            return no_update

        rows = _build_task_rows(df, pending_only=True)
        return _kpi_overlay("Tareas Pendientes", f"{len(df)} tareas pendientes", "#e74c3c", rows)

    return no_update


def _kpi_overlay(title, subtitle, color, rows):
    """Helper: builds overlay panel for KPI detail."""
    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", style={"maxWidth": "800px"}, children=[
            html.Button("✕", id="close-kpi-detail",
                         className="detail-close-btn", n_clicks=0),
            html.H3(title, className="detail-title"),
            html.P(subtitle, style={"fontSize": "0.85rem", "color": color,
                                     "fontWeight": "600", "marginBottom": "12px"}),
            html.Div(children=rows, style={"maxHeight": "65vh", "overflowY": "auto"}),
        ]),
    ])


def _build_task_rows(df, pending_only=False):
    """Helper: builds task row list from a DataFrame."""
    today = date.today()
    rows = []
    for _, r in df.iterrows():
        completed = bool(r.get("completed", 0))
        if pending_only and completed:
            continue

        due = r.get("due_on")
        if due is not None:
            try:
                d = due.date() if hasattr(due, "date") else due
                delta = (d - today).days
                if delta < 0:
                    color = "#e74c3c"
                    due_txt = f"Vencida ({abs(delta)}d)"
                elif delta <= 7:
                    color = "#e67e22"
                    due_txt = f"{delta}d"
                else:
                    color = "#666"
                    due_txt = _format_date(due)
            except Exception:
                color, due_txt = "#666", _format_date(due)
        else:
            color, due_txt = "#999", "Sin fecha"

        status_color = "#2ecc71" if completed else "#e74c3c"

        rows.append(html.Div(className="priority-task-row", children=[
            html.Div(className="priority-task-urgency",
                      style={"backgroundColor": status_color}),
            html.Div(className="priority-task-info", children=[
                html.Div(r.get("task_name", ""), className="priority-task-name",
                         style={"textDecoration": "line-through" if completed else "none"}),
                html.Div(className="priority-task-meta", children=[
                    html.Span(f"📁 {r.get('project_name', '')}"),
                    html.Span(f"👤 {r.get('assignee_name') or 'Sin asignar'}"),
                ]),
            ]),
            html.Div(className="priority-task-date", children=[
                html.Div(due_txt, style={"fontSize": "0.8rem", "fontWeight": "600",
                                          "color": color}),
            ]),
            html.A("↗", href=r.get("permalink_url", "#"), target="_blank",
                   className="priority-task-link") if r.get("permalink_url") else None,
        ]))
    return rows


# =============================================================================
# CALLBACK — PIE CHART CLICK (completadas / pendientes por proyecto)
# =============================================================================

@callback(
    Output("pie-detail-panel", "children"),
    Input({"type": "pie-project", "index": ALL}, "clickData"),
    Input("close-pie-detail", "n_clicks"),
    State("pie-project-names", "data"),
    State("ficha-owner-name", "data"),
    prevent_initial_call=True,
)
def show_pie_project_detail(all_clicks, close_clicks, project_names, owner_name):
    """Muestra tareas completadas o pendientes del proyecto clickado."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    trigger = ctx.triggered[0]["prop_id"]

    if trigger == "close-pie-detail.n_clicks":
        return [html.Button(id="close-pie-detail", style={"display": "none"}, n_clicks=0)]

    if not project_names or not owner_name:
        return no_update

    # Find which pie was clicked
    click_data = None
    pie_idx = None
    for i, cd in enumerate(all_clicks or []):
        if cd is not None:
            click_data = cd
            pie_idx = i
            break

    # Use triggered_id to find the actual clicked pie
    try:
        triggered_id = json.loads(trigger.split(".")[0])
        pie_idx = triggered_id["index"]
        click_data = all_clicks[pie_idx] if all_clicks else None
    except Exception:
        pass

    if click_data is None or pie_idx is None or pie_idx >= len(project_names):
        return no_update

    project_name = project_names[pie_idx]
    label = click_data["points"][0].get("label", "")

    if label == "Completadas":
        completed_filter = 1
        title = f"Tareas Completadas — {project_name}"
        color = "#2ecc71"
    elif label == "Pendientes":
        completed_filter = 0
        title = f"Tareas Pendientes — {project_name}"
        color = "#e74c3c"
    else:
        return no_update

    try:
        df = query_to_df("""
            SELECT t.name AS task_name, t.assignee_name, t.due_on,
                   t.completed, t.permalink_url,
                   p.name AS project_name
            FROM tasks t
            JOIN task_projects tp ON t.gid = tp.task_gid
            JOIN projects p ON tp.project_gid = p.gid
            WHERE p.owner_name = :owner AND p.name = :pname
              AND p.archived = 0 AND t.parent_gid IS NULL
              AND t.completed = :comp
            ORDER BY t.due_on IS NULL, t.due_on
        """, params={"owner": owner_name, "pname": project_name,
                     "comp": completed_filter})
        if df.empty:
            return no_update
    except Exception:
        return no_update

    rows = _build_task_rows(df)
    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", style={"maxWidth": "750px"}, children=[
            html.Button("✕", id="close-pie-detail",
                         className="detail-close-btn", n_clicks=0),
            html.H3(title, className="detail-title"),
            html.P(f"{len(df)} tareas",
                   style={"fontSize": "0.85rem", "color": color,
                          "fontWeight": "600", "marginBottom": "12px"}),
            html.Div(children=rows, style={"maxHeight": "65vh", "overflowY": "auto"}),
        ]),
    ])


# =============================================================================
# CALLBACK — PROJECT DETAIL FROM KPI PROYECTOS LIST
# =============================================================================

@callback(
    Output("ficha-project-detail-panel", "children"),
    Input({"type": "kpi-project-row", "index": ALL}, "n_clicks"),
    Input("close-ficha-project-detail", "n_clicks"),
    prevent_initial_call=True,
)
def show_ficha_project_detail(all_clicks, close_clicks):
    """Muestra detalle de proyecto al clickar en una fila de la lista KPI."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    trigger = ctx.triggered[0]["prop_id"]

    if trigger == "close-ficha-project-detail.n_clicks":
        return [html.Button(id="close-ficha-project-detail",
                            style={"display": "none"}, n_clicks=0)]

    # Find which project row was clicked
    try:
        triggered_id = json.loads(trigger.split(".")[0])
        project_gid = triggered_id["index"]
    except Exception:
        return no_update

    if not project_gid or not any(c for c in (all_clicks or []) if c):
        return no_update

    # Build project detail using estado.py's function
    detail_content = _build_project_detail(project_gid)

    # _build_project_detail returns detail-overlay > detail-panel > [close-btn, content...]
    # Extract the inner panel children, skip the original close button, add our own
    try:
        inner_panel = detail_content.children[0]  # detail-panel div
        panel_children = inner_panel.children
        # Skip the first child (original close-detail-btn) and use our own
        content_children = panel_children[1:] if len(panel_children) > 1 else panel_children
    except Exception:
        content_children = [detail_content]

    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", children=[
            html.Button("✕", id="close-ficha-project-detail",
                         className="detail-close-btn", n_clicks=0),
            *content_children,
        ]),
    ])
