"""
Página: VISIÓN GLOBAL
======================
KPIs, gráficos de proyectos por responsable/colaborador (2-col grid),
ranking de tareas delegadas (clickable), presupuesto por equipo (donut).
"""

import urllib.parse

import dash
from dash import html, dcc, callback, Output, Input, no_update
import plotly.graph_objects as go
from database import (
    get_active_projects_count,
    get_global_task_stats,
    get_projects_per_owner,
    get_projects_per_member,
    get_budget_by_portfolio,
    get_budget_by_project_portfolio,
    get_budget_by_task,
    query_to_df,
)

dash.register_page(__name__, path="/", name="Visión Global")


# =============================================================================
# HELPER BUILDERS
# =============================================================================

def _format_date(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _format_eur(v):
    return f"{v:,.0f}€".replace(",", ".")


# Mapeo manual de emails a nombres abreviados
_EMAIL_NAME_MAP = {
    "manuel.sainz@rcdeportivo.es": "M. Sainz",
}


def _abbreviate_name(name):
    """Abbreviate person name: 'Juan García Collazo' -> 'J. García'.
    Emails are mapped via _EMAIL_NAME_MAP or returned unchanged."""
    if not name:
        return name
    if "@" in name:
        return _EMAIL_NAME_MAP.get(name, name)
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {parts[1]}"
    return name


def _build_kpis():
    try:
        total_proj = int(get_active_projects_count().iloc[0]["total"])
    except Exception:
        total_proj = 0
    try:
        df_stats = get_global_task_stats()
        total_t = int(df_stats.iloc[0]["total_tareas"]) if not df_stats.empty else 0
        pend_t = int(df_stats.iloc[0]["pendientes"]) if not df_stats.empty else 0
        comp_t = int(df_stats.iloc[0]["completadas"]) if not df_stats.empty else 0
        pct = (comp_t / total_t * 100) if total_t > 0 else 0
    except Exception:
        total_t, pend_t, comp_t, pct = 0, 0, 0, 0
    try:
        df_budget = get_budget_by_portfolio()
        total_budget = int(df_budget["total_presupuesto"].sum()) if not df_budget.empty else 0
    except Exception:
        total_budget = 0

    return html.Div(className="kpis-row", children=[
        # Proyectos Activos -> link a Estado
        dcc.Link(href="/estado", style={"textDecoration": "none", "flex": "1"},
                 children=html.Div(className="kpi-card", style={"cursor": "pointer"}, children=[
            html.Div(f"{total_proj}", className="kpi-value"),
            html.Div("PROYECTOS ACTIVOS", className="kpi-label"),
        ])),
        # Tareas Completadas / Totales
        html.Div(className="kpi-card", children=[
            html.Div(style={"display": "flex", "justifyContent": "center",
                             "gap": "8px", "alignItems": "baseline"}, children=[
                html.Div(children=[
                    html.Div(f"{comp_t}", className="kpi-value", style={"color": "#2ecc71"}),
                    html.Div("COMPLETADAS", style={"fontSize": "0.6rem", "color": "#999",
                             "fontWeight": "500", "textTransform": "uppercase"}),
                ]),
                html.Div("/", style={"fontSize": "1.2rem", "color": "#999", "fontWeight": "600"}),
                html.Div(children=[
                    html.Div(f"{total_t}", className="kpi-value"),
                    html.Div("TOTALES", style={"fontSize": "0.6rem", "color": "#999",
                             "fontWeight": "500", "textTransform": "uppercase"}),
                ]),
            ]),
            html.Div("TAREAS", className="kpi-label"),
        ]),
        # % Progreso Completado
        html.Div(className="kpi-card", children=[
            html.Div(f"{pct:.0f}%", className="kpi-value", style={"color": "#2ecc71"}),
            html.Div("% PROGRESO COMPLETADO", className="kpi-label"),
        ]),
        # Presupuesto Proyectos
        html.Div(className="kpi-card", children=[
            html.Div(_format_eur(total_budget), className="kpi-value",
                     style={"color": "#1a3a5c", "fontSize": "1.3rem"}),
            html.Div("PRESUPUESTO PROYECTOS", className="kpi-label"),
        ]),
    ])


def _build_owner_chart():
    try:
        df = get_projects_per_owner()
        df = df[df["owner_name"] != "Sin asignar"]
        if df.empty:
            return html.P("Sin datos", style={"color": "#999"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})
    names, totals = df["owner_name"].tolist(), df["total"].tolist()
    short = [_abbreviate_name(n) for n in names]
    bar_labels = [f"{s}<br><b>{v}</b>" for s, v in zip(short, totals)]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(names))), y=totals, marker_color="#2c5282",
        text=bar_labels, textposition="outside",
        textfont=dict(color="#333", size=15, family="Montserrat", weight="bold"),
        hovertemplate="Ver proyectos de <b>%{customdata}</b><extra></extra>",
        customdata=names,
    ))
    fig.update_layout(
        margin=dict(b=10, t=40, l=10, r=10), height=280,
        xaxis=dict(showticklabels=False),
        yaxis=dict(showticklabels=False, range=[0, max(totals)*1.45 if totals else 1]),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return dcc.Graph(id="chart-owner", figure=fig, config={"displayModeBar": False},
                      style={"height": "280px"})


def _build_member_chart():
    try:
        df = get_projects_per_member()
        if df.empty:
            return html.P("Sin datos", style={"color": "#999"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})
    df = df[~df["user_name"].str.contains("sergioramosportela", case=False, na=False)]
    if df.empty:
        return html.P("Sin datos", style={"color": "#999"})
    names, totals = df["user_name"].tolist(), df["total"].tolist()
    short = [_abbreviate_name(n) for n in names]
    bar_labels = [f"{s}<br><b>{v}</b>" for s, v in zip(short, totals)]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(names))), y=totals, marker_color="#1a6e3a",
        text=bar_labels, textposition="outside",
        textfont=dict(color="#333", size=15, family="Montserrat", weight="bold"),
        hovertemplate="<b>%{customdata}</b><br>Proyectos: %{y}<extra></extra>",
        customdata=names,
    ))
    fig.update_layout(
        margin=dict(b=10, t=40, l=10, r=10), height=280,
        xaxis=dict(showticklabels=False),
        yaxis=dict(showticklabels=False, range=[0, max(totals)*1.5 if totals else 1]),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return dcc.Graph(id="chart-member", figure=fig, config={"displayModeBar": False},
                      style={"height": "280px"})


def _build_budget_donut():
    """Donut chart: presupuesto por portafolio."""
    try:
        df = get_budget_by_portfolio()
        if df.empty:
            return html.P("No hay datos de presupuesto", style={"color": "#999"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    portfolios = df["portfolio_name"].tolist()
    display_portfolios = [f"<b>{p}</b>" for p in portfolios]
    amounts = df["total_presupuesto"].tolist()
    total = sum(amounts)

    colors = ["#8e44ad", "#3498db", "#e67e22", "#2ecc71", "#e74c3c", "#f39c12"]

    fig = go.Figure(data=[go.Pie(
        labels=display_portfolios, values=amounts,
        hole=0.55,
        marker=dict(colors=colors[:len(portfolios)]),
        textinfo="label+percent+value",
        texttemplate="<b>%{label}</b><br>%{percent}<br>%{value:,.0f}€",
        textfont=dict(size=13, family="Montserrat", color="#1a3a5c"),
        textposition="outside",
        hovertemplate="Ver Presupuesto <b>%{customdata}</b><extra></extra>",
        customdata=portfolios,
    )])
    fig.update_layout(
        margin=dict(b=30, t=30, l=80, r=80), height=300,
        showlegend=False,
        uniformtext_minsize=10, uniformtext_mode="hide",
        annotations=[dict(text=f"<b>{_format_eur(total)}</b>", x=0.5, y=0.5,
                          font_size=18, font_family="Montserrat",
                          showarrow=False, font_color="#1a3a5c")],
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return dcc.Graph(id="chart-budget-team", figure=fig, config={"displayModeBar": False},
                      style={"height": "300px"})


def _build_delegated_ranking_chart():
    try:
        df = query_to_df("""
            SELECT t.assignee_name, COUNT(*) AS pendientes
            FROM tasks t
            JOIN task_projects tp ON t.gid = tp.task_gid
            JOIN projects p ON tp.project_gid = p.gid
            WHERE t.completed = 0 AND t.parent_gid IS NULL
              AND t.assignee_name IS NOT NULL AND p.archived = 0
              AND p.name NOT LIKE 'Tareas previamente asignadas%%'
              AND t.assignee_name NOT IN ('Ivan Sánchez', 'Iván Sánchez', 'Ivan Sanchez', 'Iván Sanchez')
              AND p.owner_name NOT IN ('Ivan Sánchez', 'Iván Sánchez', 'Ivan Sanchez', 'Iván Sanchez')
            GROUP BY t.assignee_name HAVING pendientes > 1
            ORDER BY pendientes DESC
        """)
        if df.empty:
            return html.P("Sin datos", style={"color": "#999"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    # Filtrar adicionalmente cualquier variante de Ivan Sánchez
    df = df[~df["assignee_name"].str.contains(r"[Ii]v[aá]n.*[Ss][aá]nchez", case=False, na=False, regex=True)]
    if df.empty:
        return html.P("Sin datos", style={"color": "#999"})
    
    names, counts = df["assignee_name"].tolist(), df["pendientes"].tolist()
    short = [_abbreviate_name(n) for n in names]
    bar_labels = [f"{s}<br><b>{v}</b>" for s, v in zip(short, counts)]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(names))), y=counts, marker_color="#e67e22",
        text=bar_labels, textposition="outside",
        textfont=dict(color="#333", size=15, family="Montserrat", weight="bold"),
        hovertemplate="Ver tareas de <b>%{customdata}</b><extra></extra>",
        customdata=names,
    ))
    fig.update_layout(
        margin=dict(b=10, t=40, l=10, r=10), height=250,
        xaxis=dict(showticklabels=False),
        yaxis=dict(showticklabels=False, range=[0, max(counts)*1.45 if counts else 1]),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return dcc.Graph(id="chart-delegated-ranking", figure=fig,
                     config={"displayModeBar": False},
                     style={"height": "250px"})


# =============================================================================
# LAYOUT
# =============================================================================

layout = html.Div([
    dcc.Location(id="home-url", refresh=True),
    html.Div(id="home-container", children=[]),
    html.Div(id="budget-drill-panel", children=[
        html.Button(id="close-budget-drill", style={"display": "none"}, n_clicks=0),
    ]),
    html.Div(id="delegated-ranking-detail-panel", children=[
        html.Button(id="close-deleg-ranking-detail", style={"display": "none"}, n_clicks=0),
    ]),
])


@callback(
    Output("home-container", "children"),
    Input("session-store", "data"),
)
def render_home(session):
    return html.Div(className="page-content-container", children=[
        html.Div(className="kpis-container", children=[_build_kpis()]),

        # Fila 1: Owner + Presupuesto en 2 columnas
        html.Div(className="chart-row chart-row-2col",
                 style={"marginBottom": "8px"}, children=[
            html.Div(className="graph-card", children=[
                html.H4("Número de Proyectos por Responsable",
                        style={"fontSize": "15px"}),
                html.P("Haz clic en una barra para ver la ficha",
                       style={"fontSize": "0.6rem", "color": "#999",
                              "textAlign": "center", "margin": "0 0 2px 0"}),
                _build_owner_chart(),
            ]),
            html.Div(className="graph-card", children=[
                html.H4("Presupuesto por Portafolio",
                        style={"fontSize": "15px"}),
                html.P("Haz clic en un segmento para ver el desglose",
                       style={"fontSize": "0.6rem", "color": "#999",
                              "textAlign": "center", "margin": "0 0 2px 0"}),
                _build_budget_donut(),
            ]),
        ]),

        # Fila 2: Ranking delegadas (ancho completo)
        html.Div(className="chart-row", style={"position": "relative", "zIndex": "10", "marginTop": "15px"}, children=[
            html.Div(className="graph-card", children=[
                html.H4("Ranking de Tareas Delegadas Pendientes",
                        style={"fontSize": "15px"}),
                html.P("Haz clic en una barra para ver el detalle",
                       style={"fontSize": "0.6rem", "color": "#999",
                              "textAlign": "center", "margin": "0 0 2px 0"}),
                _build_delegated_ranking_chart(),
            ]),
        ]),
    ])


# =============================================================================
# CALLBACKS — NAVEGACIÓN
# =============================================================================

@callback(Output("home-url", "href"), Input("chart-owner", "clickData"),
          prevent_initial_call=True)
def navigate_to_owner(click_data):
    if click_data and click_data.get("points"):
        name = click_data["points"][0].get("customdata", "")
        if name:
            return f"/ficha-responsable/{urllib.parse.quote(name)}"
    return no_update


# =============================================================================
# CALLBACKS — DELEGATED RANKING DRILL-DOWN
# =============================================================================

@callback(
    Output("delegated-ranking-detail-panel", "children"),
    Input("chart-delegated-ranking", "clickData"),
    Input("close-deleg-ranking-detail", "n_clicks"),
    prevent_initial_call=True,
)
def show_delegated_ranking_detail(click_data, close_clicks):
    """Muestra tareas pendientes de la persona clickada. X cierra."""
    ctx = dash.callback_context
    if ctx.triggered and ctx.triggered[0]["prop_id"] == "close-deleg-ranking-detail.n_clicks":
        return [html.Button(id="close-deleg-ranking-detail", style={"display": "none"}, n_clicks=0)]

    if not click_data or not click_data.get("points"):
        return no_update
    assignee = click_data["points"][0].get("customdata", "")
    if not assignee:
        return no_update

    try:
        df = query_to_df("""
            SELECT t.name AS task_name, t.due_on, t.permalink_url,
                   p.name AS project_name, p.owner_name
            FROM tasks t
            JOIN task_projects tp ON t.gid = tp.task_gid
            JOIN projects p ON tp.project_gid = p.gid
            WHERE t.completed = 0 AND t.parent_gid IS NULL
              AND t.assignee_name = :assignee AND p.archived = 0
              AND p.name NOT LIKE 'Tareas previamente asignadas%%'
              AND p.owner_name NOT IN ('Ivan Sánchez', 'Iván Sánchez', 'Ivan Sanchez', 'Iván Sanchez')
            ORDER BY t.due_on IS NULL, t.due_on
        """, params={"assignee": assignee})
        if df.empty:
            return None
    except Exception:
        return None

    rows = []
    for _, r in df.iterrows():
        rows.append(html.Div(className="priority-task-row", children=[
            html.Div(className="priority-task-urgency",
                      style={"backgroundColor": "#e67e22"}),
            html.Div(className="priority-task-info", children=[
                html.Div(r["task_name"], className="priority-task-name"),
                html.Div(className="priority-task-meta", children=[
                    html.Span(f"📁 {r.get('project_name', '')}"),
                    html.Span(f"👤 Asignada por: {r.get('owner_name', '—')}"),
                ]),
            ]),
            html.Div(className="priority-task-date", children=[
                html.Div(_format_date(r.get("due_on")),
                         style={"fontSize": "0.8rem", "fontWeight": "600"}),
            ]),
            html.A("↗", href=r.get("permalink_url", "#"), target="_blank",
                   className="priority-task-link") if r.get("permalink_url") else None,
        ]))

    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", style={"maxWidth": "750px"}, children=[
            html.Button("✕", id="close-deleg-ranking-detail",
                         className="detail-close-btn", n_clicks=0),
            html.H3(f"Tareas pendientes: {assignee}", className="detail-title"),
            html.P(f"{len(df)} tareas asignadas pendientes",
                   style={"fontSize": "0.85rem", "color": "#e67e22",
                          "fontWeight": "600", "marginBottom": "12px"}),
            html.Div(children=rows, style={"maxHeight": "60vh", "overflowY": "auto"}),
        ]),
    ])


# =============================================================================
# CALLBACKS — PRESUPUESTO DRILL-DOWN
# =============================================================================

@callback(
    Output("budget-drill-panel", "children"),
    Input("chart-budget-team", "clickData"),
    Input("close-budget-drill", "n_clicks"),
    prevent_initial_call=True,
)
def show_budget_team_drill(click_data, close_clicks):
    ctx = dash.callback_context
    if ctx.triggered and ctx.triggered[0]["prop_id"] == "close-budget-drill.n_clicks":
        return [html.Button(id="close-budget-drill", style={"display": "none"}, n_clicks=0)]
    if not click_data or not click_data.get("points"):
        return no_update

    # For donut, customdata is the portfolio name
    point = click_data["points"][0]
    portfolio_name = point.get("customdata", "") or point.get("label", "")
    if not portfolio_name:
        return no_update

    try:
        df = get_budget_by_project_portfolio(portfolio_name)
        if df.empty:
            return None
    except Exception:
        return None

    total = df["total_presupuesto"].sum()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["project_name"], y=df["total_presupuesto"], marker_color="#9b59b6",
        text=[_format_eur(v) for v in df["total_presupuesto"]],
        textposition="outside",
        textfont=dict(color="#333", size=10, family="Montserrat", weight="bold"),
        customdata=list(zip(df["project_gid"].tolist(), df["project_name"].tolist())),
        hovertemplate="Ver presupuesto de <b>%{customdata[1]}</b><extra></extra>",
    ))
    fig.update_layout(
        margin=dict(b=80, t=10, l=20, r=20), height=400,
        xaxis=dict(tickfont=dict(size=9, family="Montserrat"), tickangle=-30),
        yaxis=dict(showticklabels=False),
        plot_bgcolor="white", paper_bgcolor="white",
    )

    return html.Div(className="detail-overlay", children=[
        html.Div(className="detail-panel", style={"maxWidth": "950px"}, children=[
            html.Button("✕", id="close-budget-drill",
                         className="detail-close-btn", n_clicks=0),
            html.H3(f"Presupuesto: {portfolio_name}", className="detail-title"),
            html.P(f"Total: {_format_eur(total)}",
                   style={"fontSize": "0.9rem", "color": "#8e44ad",
                          "fontWeight": "700", "marginBottom": "10px"}),
            html.P("Haz clic en un proyecto para ver el desglose por tareas",
                   style={"fontSize": "0.75rem", "color": "#999", "textAlign": "center"}),
            dcc.Graph(id="chart-budget-project", figure=fig,
                      config={"displayModeBar": False}),
            html.Div(id="budget-task-detail"),
        ]),
    ])


@callback(Output("budget-task-detail", "children"),
          Input("chart-budget-project", "clickData"), prevent_initial_call=True)
def show_budget_task_drill(click_data):
    if not click_data or not click_data.get("points"):
        return no_update
    cd = click_data["points"][0].get("customdata", [])
    project_gid = cd[0] if isinstance(cd, (list, tuple)) and len(cd) > 0 else ""
    project_name = cd[1] if isinstance(cd, (list, tuple)) and len(cd) > 1 else click_data["points"][0].get("x", "")
    if not project_gid:
        return no_update
    try:
        df = get_budget_by_task(project_gid)
        if df.empty:
            return html.P("No hay tareas con presupuesto", style={"color": "#999"})
    except Exception:
        return None

    rows = []
    for _, r in df.iterrows():
        rows.append(html.Div(className="priority-task-row", children=[
            html.Div(className="priority-task-urgency", style={"backgroundColor": "#8e44ad"}),
            html.Div(className="priority-task-info", children=[
                html.Div(r["task_name"], className="priority-task-name"),
                html.Div(className="priority-task-meta", children=[
                    html.Span(f"📋 {r['custom_field_name']}"),
                    html.Span(f"👤 {r.get('assignee_name') or 'Sin asignar'}"),
                ]),
            ]),
            html.Div(className="priority-task-date", children=[
                html.Div(_format_eur(r["presupuesto"]),
                         style={"fontSize": "0.85rem", "fontWeight": "700", "color": "#8e44ad"}),
            ]),
        ]))
    total = df["presupuesto"].sum()
    return html.Div(style={"marginTop": "15px"}, children=[
        html.Hr(style={"border": "none", "borderTop": "1px solid #eee"}),
        html.Strong(f"Tareas — {project_name}", style={"fontSize": "0.85rem", "color": "#1a3a5c"}),
        html.Span(f"  Total: {_format_eur(total)}",
                  style={"fontSize": "0.8rem", "color": "#8e44ad", "fontWeight": "600"}),
        html.Div(children=rows, style={"marginTop": "8px"}),
    ])
