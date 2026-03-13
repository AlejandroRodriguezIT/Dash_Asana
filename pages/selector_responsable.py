"""
Página: FICHA DE RESPONSABLE (Selector)
=========================================
Muestra un grid con las fotos y nombres de todos los responsables.
Al hacer clic en uno, navega a la ficha detallada del responsable.
"""

import os
import urllib.parse

import dash
from dash import html, dcc
from database import get_owners_list

dash.register_page(
    __name__,
    path="/fichas-responsables",
    name="Ficha de Responsable",
)

# Carpeta de imágenes de responsables
_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "Responsables")

# Mapeo: nombre del owner → nombre del archivo de imagen (sin extensión)
# Se busca coincidencia parcial entre el nombre de archivo y el owner_name.
def _load_image_map():
    """Carga los archivos de imagen disponibles y construye el mapeo."""
    img_map = {}
    try:
        files = os.listdir(_IMG_DIR)
    except Exception:
        return img_map

    for f in files:
        name_no_ext, ext = os.path.splitext(f)
        if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            if name_no_ext.lower() != "defecto":
                img_map[name_no_ext] = f

    return img_map


def _get_image_path(owner_name):
    """Encuentra la imagen más adecuada para un responsable.

    Busca coincidencia parcial entre el nombre del archivo y el owner_name.
    Si no hay coincidencia, devuelve Defecto.png.
    """
    img_map = _load_image_map()

    # Coincidencia exacta
    if owner_name in img_map:
        return f"/assets/Responsables/{img_map[owner_name]}"

    # Coincidencia parcial: verificar si el nombre del archivo está contenido
    # en el owner_name o viceversa
    owner_lower = owner_name.lower()
    for file_name, file_path in img_map.items():
        file_lower = file_name.lower()
        # El nombre del archivo está contenido en el owner o viceversa
        if file_lower in owner_lower or owner_lower in file_lower:
            return f"/assets/Responsables/{file_path}"
        # Coincidencia por primer nombre + primer apellido
        file_parts = file_lower.split()
        owner_parts = owner_lower.split()
        if len(file_parts) >= 2 and len(owner_parts) >= 2:
            if file_parts[0] == owner_parts[0] and file_parts[1][:4] == owner_parts[1][:4]:
                return f"/assets/Responsables/{file_path}"

    return "/assets/Responsables/Defecto.png"


def _build_responsable_card(owner_name):
    """Construye una tarjeta con imagen circular y nombre del responsable."""
    img_src = _get_image_path(owner_name)
    href = f"/ficha-responsable/{urllib.parse.quote(owner_name)}"

    return dcc.Link(
        href=href,
        className="responsable-card",
        children=[
            html.Img(src=img_src, className="responsable-img"),
            html.Div(owner_name, className="responsable-name"),
        ],
    )


# =============================================================================
# LAYOUT
# =============================================================================

def layout(**kwargs):
    try:
        df = get_owners_list()
        # Excluir 'Sin asignar'
        owners = [r["owner_name"] for _, r in df.iterrows()
                  if r["owner_name"] != "Sin asignar"]
    except Exception:
        owners = []

    cards = [_build_responsable_card(name) for name in owners]

    return html.Div([
        html.Div(className="responsable-grid", children=cards),
    ])
