"""
Página: FICHA DE PROVEEDOR
============================
Vista detallada de un proveedor/colaborador con:
- Proyectos en los que participa
- Tareas asignadas (completadas y pendientes)
- Presupuestos asignados por proyecto (custom fields numéricos)
"""

import dash
from dash import html, dcc
import plotly.graph_objects as go
import urllib.parse
from datetime import date
from database import (
    get_projects_for_member,
    get_member_tasks_assigned,
    get_member_custom_field_budgets,
)

dash.register_page(
    __name__,
    path_template="/ficha-proveedor/<user_name>",
    name="Ficha Proveedor",
)


def _format_date(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _format_number(val):
    try:
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(val)


def _build_project_card(row):
    """Tarjeta de proyecto en el que participa el proveedor."""
    total = int(row.get("total_tareas", 0))
    comp = int(row.get("tareas_completadas", 0))
    pct = (comp / total * 100) if total > 0 else 0

    meta = []
    if row.get("owner_name"):
        meta.append(html.Span(["👤 Responsable: ", str(row["owner_name"])]))
    if row.get("team_name"):
        meta.append(html.Span(["🏠 ", str(row["team_name"])]))
    if row.get("due_on"):
        meta.append(html.Span(["📅 ", _format_date(row["due_on"])]))

    return html.Div(
        className="project-card",
        style={"borderLeftColor": "#1a6e3a"},
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
                html.Div(f"{pct:.0f}% completado", className="progress-text"),
            ]),
        ]
    )


def _build_tasks_chart(user_name):
    """Gráfico de tareas del proveedor por proyecto (completadas vs pendientes)."""
    try:
        df = get_member_tasks_assigned(user_name)
        if df.empty:
            return html.P("No hay tareas asignadas directamente",
                          style={"color": "#999", "fontSize": "0.85rem"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    # Agrupar por proyecto
    summary = df.groupby("project_name").agg(
        completadas=("completed", "sum"),
        total=("completed", "count"),
    ).reset_index()
    summary["pendientes"] = summary["total"] - summary["completadas"]
    summary = summary.sort_values("pendientes", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Completadas",
        x=summary["project_name"],
        y=summary["completadas"],
        marker_color="#2ecc71",
        text=summary["completadas"].astype(int),
        textposition="inside",
        textfont=dict(size=10, family="Montserrat", weight="bold"),
    ))
    fig.add_trace(go.Bar(
        name="Pendientes",
        x=summary["project_name"],
        y=summary["pendientes"],
        marker_color="#e74c3c",
        text=summary["pendientes"].astype(int),
        textposition="inside",
        textfont=dict(size=10, family="Montserrat", weight="bold"),
    ))

    fig.update_layout(
        barmode="stack",
        margin=dict(b=60, t=5, l=20, r=20),
        height=300,
        legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center"),
        xaxis=dict(tickfont=dict(size=9, family="Montserrat"), tickangle=-25),
        yaxis=dict(showticklabels=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _build_budget_chart(user_name):
    """
    Gráfico de presupuestos/valores numéricos de custom fields
    asociados al proveedor por proyecto.
    """
    try:
        df = get_member_custom_field_budgets(user_name)
        if df.empty:
            return html.P("No se han encontrado campos de presupuesto en los proyectos",
                          style={"color": "#999", "fontSize": "0.85rem"})
    except Exception:
        return html.P("Error cargando datos", style={"color": "#e74c3c"})

    # Agrupar por proyecto y campo
    grouped = df.groupby(["project_name", "custom_field_name"])["number_value"].sum().reset_index()

    if grouped.empty:
        return html.P("Sin datos de presupuesto", style={"color": "#999"})

    # Si hay múltiples campos, crear un gráfico por campo
    fields = grouped["custom_field_name"].unique()

    charts = []
    for field in fields:
        df_field = grouped[grouped["custom_field_name"] == field].sort_values(
            "number_value", ascending=False
        )

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_field["project_name"],
            y=df_field["number_value"],
            marker_color="#3498db",
            text=[_format_number(v) for v in df_field["number_value"]],
            textposition="outside",
            textfont=dict(color="#333", size=10, family="Montserrat", weight="bold"),
            hovertemplate="<b>%{x}</b><br>%{y:,.2f}<extra></extra>",
        ))

        max_y = df_field["number_value"].max() * 1.25 if not df_field.empty else 1
        fig.update_layout(
            margin=dict(b=60, t=5, l=20, r=20),
            height=300,
            xaxis=dict(tickfont=dict(size=9, family="Montserrat"), tickangle=-25),
            yaxis=dict(showticklabels=False, range=[0, max_y]),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )

        charts.append(html.Div(className="graph-card full-width", children=[
            html.H4(f"{field} por Proyecto"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ]))

    return html.Div(children=charts)


def _build_budget_summary_table(user_name):
    """Tabla resumen de valores numéricos (presupuestos) por proyecto."""
    try:
        df = get_member_custom_field_budgets(user_name)
        if df.empty:
            return None
    except Exception:
        return None

    rows = []
    for _, r in df.iterrows():
        rows.append(html.Tr([
            html.Td(r["project_name"], style={"fontSize": "0.8rem"}),
            html.Td(r["custom_field_name"], style={"fontSize": "0.8rem"}),
            html.Td(
                r.get("display_value") or _format_number(r["number_value"]),
                style={"fontSize": "0.8rem", "textAlign": "right", "fontWeight": "600"}
            ),
        ]))

    if not rows:
        return None

    return html.Table(
        style={"width": "100%", "borderCollapse": "collapse"},
        children=[
            html.Thead(html.Tr([
                html.Th("Proyecto", style={"textAlign": "left", "padding": "8px",
                                           "borderBottom": "2px solid #ddd",
                                           "fontSize": "0.8rem", "color": "#1a3a5c"}),
                html.Th("Campo", style={"textAlign": "left", "padding": "8px",
                                        "borderBottom": "2px solid #ddd",
                                        "fontSize": "0.8rem", "color": "#1a3a5c"}),
                html.Th("Valor", style={"textAlign": "right", "padding": "8px",
                                        "borderBottom": "2px solid #ddd",
                                        "fontSize": "0.8rem", "color": "#1a3a5c"}),
            ])),
            html.Tbody(rows),
        ]
    )


def _build_pending_tasks_list(user_name):
    """Lista de tareas pendientes asignadas al proveedor."""
    try:
        df = get_member_tasks_assigned(user_name)
        if df.empty:
            return html.P("No hay tareas asignadas", style={"color": "#999"})
        df_pending = df[df["completed"] == 0]
        if df_pending.empty:
            return html.P("Todas las tareas están completadas 🎉",
                          style={"color": "#2ecc71", "fontWeight": "600"})
    except Exception:
        return html.P("Error", style={"color": "#e74c3c"})

    today = date.today()
    items = []
    for _, t in df_pending.head(20).iterrows():
        due = t.get("due_on")
        if due is not None:
            try:
                d = due.date() if hasattr(due, "date") else due
                delta = (d - today).days
                if delta < 0:
                    cls, txt = "task-due overdue", f"Vencida ({abs(delta)}d)"
                elif delta <= 7:
                    cls, txt = "task-due upcoming", f"{delta}d"
                else:
                    cls, txt = "task-due normal", _format_date(due)
            except Exception:
                cls, txt = "task-due normal", _format_date(due)
        else:
            cls, txt = "task-due normal", "—"

        items.append(html.Li(className="task-item", children=[
            html.Div(className="task-check"),
            html.Div(children=[
                html.Div(t.get("task_name", ""), className="task-name"),
                html.Div(t.get("project_name", ""),
                         style={"fontSize": "0.7rem", "color": "#999"}),
            ], style={"flex": "1"}),
            html.Div(txt, className=cls),
        ]))

    remaining = len(df_pending) - 20
    if remaining > 0:
        items.append(html.Li(
            style={"padding": "10px", "textAlign": "center",
                   "color": "#999", "fontSize": "0.8rem"},
            children=f"... y {remaining} tareas más"
        ))

    return html.Ul(className="task-list", children=items)


# =============================================================================
# LAYOUT
# =============================================================================

def layout(user_name=None, **kwargs):
    if not user_name:
        return html.Div([
            dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),
            html.P("No se especificó un proveedor", style={"color": "#999"}),
        ])

    user_name = urllib.parse.unquote(user_name)

    # Obtener datos
    try:
        df_projects = get_projects_for_member(user_name)
    except Exception as e:
        return html.Div([
            dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),
            html.P(f"Error: {e}", style={"color": "#e74c3c"}),
        ])

    try:
        df_tasks = get_member_tasks_assigned(user_name)
        total_tasks = len(df_tasks) if not df_tasks.empty else 0
        pend_tasks = int((df_tasks["completed"] == 0).sum()) if not df_tasks.empty else 0
        comp_tasks = total_tasks - pend_tasks
    except Exception:
        total_tasks, pend_tasks, comp_tasks = 0, 0, 0

    total_proj = len(df_projects)
    pct_comp = (comp_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return html.Div([
        dcc.Link("← Volver a Visión Global", href="/", className="back-btn"),

        html.H2(f"Ficha de Proveedor: {user_name}", className="page-title"),
        html.P(f"Participa en {total_proj} proyectos", className="page-subtitle"),

        # KPIs
        html.Div(className="kpis-container", children=[
            html.Div(className="kpis-row", children=[
                html.Div(className="kpi-card", children=[
                    html.Div(str(total_proj), className="kpi-value"),
                    html.Div("PROYECTOS", className="kpi-label"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div(str(total_tasks), className="kpi-value"),
                    html.Div("TAREAS ASIGNADAS", className="kpi-label"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div(str(pend_tasks), className="kpi-value",
                             style={"color": "#e74c3c"}),
                    html.Div("PENDIENTES", className="kpi-label"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div(f"{pct_comp:.0f}%", className="kpi-value",
                             style={"color": "#2ecc71"}),
                    html.Div("COMPLETADO", className="kpi-label"),
                ]),
            ]),
        ]),

        # Proyectos en los que participa
        html.Div(className="section-container", children=[
            html.H3("Proyectos en los que Participa", className="section-title-bar"),
        ] + (
            [_build_project_card(row) for _, row in df_projects.iterrows()]
            if not df_projects.empty else
            [html.P("No participa en proyectos activos", style={"color": "#999"})]
        )),

        # Gráficos
        html.Div(className="graphs-container", children=[
            # Tareas por proyecto
            html.Div(className="graphs-row", children=[
                html.Div(className="graph-card full-width", children=[
                    html.H4("Tareas Asignadas por Proyecto"),
                    _build_tasks_chart(user_name),
                ]),
            ]),

            # Presupuestos
            html.Div(className="graphs-row", children=[
                html.Div(className="graph-card full-width", children=[
                    html.H4("Presupuestos / Valores Numéricos por Proyecto"),
                    _build_budget_chart(user_name),
                ]),
            ]),
        ]),

        # Tabla resumen presupuestos
        html.Div(className="section-container", children=[
            html.H3("Detalle de Valores Numéricos (Presupuestos)", className="section-title-bar"),
            _build_budget_summary_table(user_name) or
            html.P("No hay datos de presupuesto disponibles. Los presupuestos se detectan "
                   "automáticamente desde los campos personalizados numéricos de Asana.",
                   style={"color": "#999", "fontSize": "0.85rem"}),
        ]),

        # Tareas pendientes
        html.Div(className="section-container", children=[
            html.H3("Tareas Pendientes", className="section-title-bar"),
            _build_pending_tasks_list(user_name),
        ]),
    ])
