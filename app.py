"""
Plataforma de Gestión de Proyectos (Asana)
============================================
RC Deportivo de La Coruña
"""

import dash
from dash import html, dcc, callback, Output, Input, State, no_update
import dash_bootstrap_components as dbc
from database import init_users_table, validate_user

# Inicializar tabla de usuarios al arrancar
try:
    init_users_table()
except Exception as e:
    print(f"Aviso: No se pudo inicializar tabla de usuarios: {e}")

# Inicializar la aplicación
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    use_pages=True,
    pages_folder="pages"
)

app.title = "Gestión de Proyectos - RC Deportivo"
server = app.server

# =============================================================================
# MAPA DE SECCIONES → PERMISOS
# =============================================================================
# 0 = acceso global (todas las secciones)
# 1 = Visión Global
# 2 = Estado de los Proyectos

SECCIONES = {
    "vision_global": {
        "permiso": 1,
        "label": "VISIÓN GLOBAL",
        "icon": "📊",
        "href": "/",
        "id": "nav-vision",
    },
    "estado": {
        "permiso": 2,
        "label": "ESTADO DE LOS PROYECTOS",
        "icon": "📋",
        "href": "/estado",
        "id": "nav-estado",
    },
    "tareas_prioritarias": {
        "permiso": 3,
        "label": "TAREAS PRIORITARIAS",
        "icon": "⚡",
        "href": "/tareas-prioritarias",
        "id": "nav-tareas-prio",
    },
    "fichas_responsables": {
        "permiso": 4,
        "label": "FICHA DE RESPONSABLE",
        "icon": "👤",
        "href": "/fichas-responsables",
        "id": "nav-fichas-resp",
    },
}


# =============================================================================
# COMPONENTES
# =============================================================================

def create_login():
    """Crea la pantalla de login."""
    return html.Div(
        className="login-wrapper",
        id="login-wrapper",
        children=[
            html.Div(
                className="login-box",
                children=[
                    html.Img(src="/assets/escudo.png", className="login-shield"),
                    html.H2("Iniciar Sesión", className="login-title"),
                    dcc.Input(
                        id="login-user",
                        type="text",
                        placeholder="Usuario",
                        className="login-input",
                        autoFocus=True,
                    ),
                    dcc.Input(
                        id="login-pass",
                        type="password",
                        placeholder="Contraseña",
                        className="login-input",
                        n_submit=0,
                    ),
                    html.Div(id="login-error", className="login-error"),
                    html.Button("Entrar", id="login-btn",
                                className="login-btn", n_clicks=0),
                ]
            )
        ]
    )


def create_header():
    """Crea el encabezado principal."""
    return html.Div(
        className="main-header",
        children=[
            html.Div(
                className="header-content",
                children=[
                    html.Img(src="/assets/escudo.png", className="header-logo"),
                    html.Div([
                        html.H1("Gestión de Proyectos",
                                className="header-title"),
                        html.P("RC Deportivo - Plataforma Asana",
                               className="header-subtitle"),
                    ])
                ]
            )
        ]
    )


# =============================================================================
# LAYOUT PRINCIPAL
# =============================================================================

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='session-store', storage_type='session'),
    html.Div(id='resize-trigger', style={'display': 'none'}),
    # Login overlay
    create_login(),
    # App principal (oculta hasta login)
    html.Div(
        className="app-container",
        id="app-container",
        style={"display": "none"},
        children=[
            # Sidebar
            html.Div(
                className="sidebar",
                id="sidebar",
                children=[
                    html.Div(
                        className="sidebar-header",
                        children=[html.H2("DEPORTIVO", className="sidebar-title")]
                    ),
                    html.Nav(className="sidebar-nav", id="sidebar-nav"),
                    html.Div(
                        className="sidebar-footer",
                        id="sidebar-footer",
                        children=[
                            html.Div(id="user-info-text", className="user-info"),
                            html.Div(id="user-role-text", className="user-role"),
                            html.Button("Cerrar sesión", id="btn-logout",
                                        className="btn-logout", n_clicks=0),
                        ]
                    ),
                ]
            ),
            html.Div(
                className="main-content",
                children=[
                    create_header(),
                    html.Div(id="page-content", children=[dash.page_container])
                ]
            )
        ]
    )
])


# =============================================================================
# CALLBACKS
# =============================================================================

@callback(
    Output('session-store', 'data'),
    Output('login-error', 'children'),
    Input('login-btn', 'n_clicks'),
    Input('login-pass', 'n_submit'),
    State('login-user', 'value'),
    State('login-pass', 'value'),
    State('session-store', 'data'),
    prevent_initial_call=True,
)
def do_login(n_clicks, n_submit, usuario, contrasena, current_session):
    """Valida credenciales y guarda la sesión."""
    if current_session and current_session.get('authenticated'):
        return no_update, no_update
    if not usuario or not contrasena:
        return no_update, "Introduce usuario y contraseña"
    user = validate_user(usuario, contrasena)
    if user:
        return {
            "authenticated": True,
            "usuario": user["usuario"],
            "permisos": user["permisos"],
            "nombre": user["nombre"],
            "rol": user["rol"],
        }, ""
    return no_update, "Credenciales incorrectas"


@callback(
    Output('session-store', 'data', allow_duplicate=True),
    Input('btn-logout', 'n_clicks'),
    prevent_initial_call=True,
)
def do_logout(n_clicks):
    """Cierra sesión limpiando el store."""
    if n_clicks:
        return {"authenticated": False}
    return no_update


@callback(
    Output('login-wrapper', 'style'),
    Output('app-container', 'style'),
    Output('sidebar-nav', 'children'),
    Output('user-info-text', 'children'),
    Output('user-role-text', 'children'),
    Input('session-store', 'data'),
    Input('url', 'pathname'),
)
def toggle_login(session, pathname):
    """Muestra login u app según sesión. Construye sidebar según permisos."""
    if not session or not session.get('authenticated'):
        return (
            {"display": "flex"},
            {"display": "none"},
            [], "", "",
        )

    if pathname is None:
        pathname = "/"

    permisos_raw = str(session.get('permisos', '0'))
    permisos_list = [p.strip() for p in permisos_raw.split(',')]
    is_global = '0' in permisos_list

    # Mapa de rutas para determinar estado activo
    path_map = {
        "vision_global": "/",
        "estado": "/estado",
        "tareas_prioritarias": "/tareas-prioritarias",
        "fichas_responsables": "/fichas-responsables",
    }

    nav_items = []
    for key, sec in SECCIONES.items():
        if is_global or str(sec['permiso']) in permisos_list:
            base = path_map.get(key, "/__none__")
            is_active = (pathname == base) or (
                base != "/" and pathname.startswith(base)
            )
            # Visión global: activa también para /proyectos/...
            if key == "vision_global" and pathname.startswith("/proyectos"):
                is_active = True
            # Ficha responsable: activa también para /ficha-responsable/<name>
            if key == "fichas_responsables" and pathname.startswith("/ficha-responsable/"):
                is_active = True
            cls = "nav-link active" if is_active else "nav-link"
            nav_items.append(
                dcc.Link([
                    html.Span(sec['icon'], className="nav-icon-text"),
                    html.Span(sec['label'])
                ], href=sec['href'], className=cls, id=sec['id'])
            )

    nombre = session.get('nombre', session.get('usuario', ''))
    rol = session.get('rol', '')

    return (
        {"display": "none"},
        {"display": "flex"},
        nav_items,
        f"Usuario: {nombre}",
        rol,
    )


# =============================================================================
# CLIENTSIDE: forzar resize tras login para que Plotly recalcule
# =============================================================================

app.clientside_callback(
    """
    function(containerStyle) {
        if (containerStyle && containerStyle.display !== 'none') {
            setTimeout(function() {
                window.dispatchEvent(new Event('resize'));
            }, 200);
            setTimeout(function() {
                window.dispatchEvent(new Event('resize'));
            }, 600);
        }
        return '';
    }
    """,
    Output('resize-trigger', 'children'),
    Input('app-container', 'style'),
)


# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    app.run(debug=True, port=8051)
