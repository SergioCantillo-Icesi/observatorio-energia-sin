"""
theme.py — Identidad visual ICESI compartida por TODAS las páginas del
Observatorio Energético SIN.

Fuente: manual de identidad institucional vigente
(https://www.icesi.edu.co/wp-content/uploads/2026/03/Manual-de-marca-institucional-Icesi.pdf)
  - Azul Icesi: Pantone 2131 C = RGB(84,84,233) = #5454E9 (color OFICIAL
    confirmado en el manual — los conversores genéricos de Pantone→HEX dan
    un azul distinto, no los uses).
  - Paleta principal institucional = solo Azul Icesi + Blanco.
  - Gris 1 (Pantone 423 C, ≈ #898D8D) como neutro de apoyo (documentado en
    manuales de facultades/centros para textos secundarios).
  - Tipografía: Plus Jakarta Sans.
  - COLOR_ALERT (rojo) NO viene del manual — no encontré paleta de alerta
    secundaria oficial confirmada. Es la única excepción deliberada, para
    que el año de sequía / señales de riesgo se lean como advertencia.
    Cámbialo aquí si consigues los colores secundarios oficiales.

Dos piezas de este esquema, cada una cubre lo que la otra no puede:

  1. `.streamlit/config.toml` en la raíz del proyecto — define el tema base
     de Streamlit (fondo blanco, color primario, color de texto). Esto lo
     recoge Streamlit automáticamente para TODA la app, página por página,
     sin que cada página tenga que llamar nada. Es lo que evita que el
     tema oscuro del navegador/SO del usuario se imponga sobre la app.

  2. `apply_icesi_theme()` — cubre lo que config.toml NO puede: la
     tipografía Plus Jakarta Sans (Streamlit solo permite "sans serif" /
     "serif" / "monospace" genéricos ahí, no fuentes de Google Fonts), y
     ajustes finos de componentes específicos (zona de gráficos, expander,
     botones, dataframe).

Uso en cada página nueva:
    from sala_control.theme import apply_icesi_theme, ICESI_BLUE, ...
    apply_icesi_theme()   # llamar una sola vez, al inicio, antes de cualquier otro st.*
"""
FONT_FAMILY = "Plus Jakarta Sans, Arial, sans-serif"

ICESI_BLUE = "#5454E9"
ICESI_BLUE_DARK = "#2E2E8F"
ICESI_BLUE_LIGHT = "#EEF0FC"     # fondo sutil para tarjetas/expanders/hover
ICESI_GRAY = "#898D8D"
ICESI_GRAY_LIGHT = "#C7C9C9"
ICESI_ALERT = "#B23A48"          # ver nota arriba — no es color oficial del manual
ICESI_TEXT = "#1A1A2E"


def apply_icesi_theme() -> None:
    """Inyecta la tipografía y los ajustes finos de estilo ICESI. Llamar
    una sola vez por página, al inicio (idealmente justo después de
    st.set_page_config()).

    El import de streamlit se hace AQUÍ ADENTRO (no al nivel del módulo) a
    propósito: así los módulos de gráficos/analytics pueden importar las
    constantes de color de este archivo (ICESI_BLUE, etc.) sin arrastrar
    una dependencia dura de streamlit — útil para los scripts de prueba
    sueltos que generan HTML con Plotly directamente, sin levantar la app."""
    import streamlit as st

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"], [data-testid="stMarkdownContainer"] {{
        font-family: {FONT_FAMILY} !important;
    }}

    /* Fuerza fondo blanco institucional sin importar el tema oscuro del
       navegador/SO del usuario */
    [data-testid="stAppViewContainer"], [data-testid="stHeader"],
    [data-testid="stToolbar"] {{
        background-color: #FFFFFF !important;
    }}
    body, .main {{
        color: {ICESI_TEXT} !important;
    }}

    /* Zona de gráficos (st.plotly_chart) — tarjeta clara con borde suave,
       para que el gráfico (fondo blanco) contraste contra el fondo blanco
       de la página en vez de fundirse con él. Mismo lenguaje visual que
       expanders y tarjetas KPI. */
    [data-testid="stPlotlyChart"] {{
        background-color: #F7F8FC !important;
        border: 1px solid {ICESI_BLUE_LIGHT} !important;
        border-radius: 12px !important;
        padding: 12px !important;
        box-shadow: 0 2px 8px rgba(84,84,233,0.08) !important;
    }}
    /* st.container(height=...) (data-testid="stContainer") — usado para
       las pestañas de participación, donde el gráfico necesita scroll
       propio si hay muchas categorías. Streamlit ya le pone su propio
       fondo/borde por defecto; se lo reemplaza por la MISMA tarjeta de
       arriba para que sea el único marco visible, y el stPlotlyChart de
       adentro se resetea a "sin marco propio" para que el gráfico ocupe
       el 100% del espacio sin una segunda tarjeta anidada de otro color. */
    [data-testid="stContainer"] {{
        background-color: #F7F8FC !important;
        border: 1px solid {ICESI_BLUE_LIGHT} !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(84,84,233,0.08) !important;
    }}
    [data-testid="stContainer"] [data-testid="stPlotlyChart"] {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        width: 100% !important;
        height: 100% !important;
    }}

    /* Encabezados */
    h1, h2, h3 {{
        font-family: {FONT_FAMILY} !important;
        font-weight: 800 !important;
        color: {ICESI_TEXT} !important;
    }}

    /* Expanders */
    [data-testid="stExpander"] summary {{
        font-weight: 600 !important;
        color: {ICESI_BLUE} !important;
    }}
    [data-testid="stExpander"] {{
        border-color: {ICESI_BLUE_LIGHT} !important;
    }}

    /* Botones */
    .stButton>button, .stDownloadButton>button {{
        background-color: {ICESI_BLUE} !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }}
    .stButton>button:hover, .stDownloadButton>button:hover {{
        background-color: {ICESI_BLUE_DARK} !important;
    }}

    /* Checkboxes / radio / selección */
    [data-testid="stCheckbox"] label, [data-testid="stRadio"] label {{
        color: {ICESI_TEXT} !important;
    }}

    /* Dataframes */
    [data-testid="stDataFrame"] {{
        font-family: {FONT_FAMILY} !important;
    }}

    /* Sidebar de navegación (st.navigation) — fondo claro de marca y
       resaltado del ítem activo en Azul Icesi, para que la navegación se
       sienta parte de la misma identidad, no un widget genérico de
       Streamlit sin estilizar. */
    [data-testid="stSidebar"] {{
        background-color: {ICESI_BLUE_LIGHT} !important;
        border-right: 1px solid {ICESI_GRAY_LIGHT};
    }}
    [data-testid="stSidebarNav"] a {{
        border-radius: 6px !important;
        font-weight: 500 !important;
        color: {ICESI_TEXT} !important;
    }}
    [data-testid="stSidebarNav"] a:hover {{
        background-color: rgba(84, 84, 233, 0.12) !important;
    }}
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background-color: {ICESI_BLUE} !important;
        color: white !important;
        font-weight: 700 !important;
    }}
    [data-testid="stSidebarNav"] a[aria-current="page"] span {{
        color: white !important;
    }}

    /* Captions */
    [data-testid="stCaptionContainer"] {{
        color: {ICESI_GRAY} !important;
    }}

    /* Pestañas (st.tabs) — mismo lenguaje visual que la barra lateral de
       navegación (chip sólido en Azul Icesi para la pestaña activa), para
       que "todo el tab" (reposo, hover y selección) quede bajo una sola
       paleta en vez del indicador genérico de Streamlit. Streamlit
       renderiza cada pestaña como un <div data-testid="stTab" role="tab">,
       NO como un <button> — el selector tiene que apuntar a eso. */
    [data-testid="stTabs"] [role="tablist"] {{
        gap: 4px;
        border-bottom: 1px solid {ICESI_BLUE_LIGHT} !important;
    }}
    [data-testid="stTabs"] [data-testid="stTab"] {{
        color: {ICESI_GRAY} !important;
        font-weight: 600 !important;
        background-color: transparent !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 8px 16px !important;
    }}
    [data-testid="stTabs"] [data-testid="stTab"] p {{
        color: inherit !important;
    }}
    [data-testid="stTabs"] [data-testid="stTab"]:hover {{
        color: {ICESI_BLUE} !important;
        background-color: {ICESI_BLUE_LIGHT} !important;
    }}
    [data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"],
    [data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"]:hover {{
        color: white !important;
        background-color: {ICESI_BLUE} !important;
        font-weight: 700 !important;
    }}
    /* Oculta el indicador nativo de selección (subrayado) — ya no hace
       falta, la pestaña activa se distingue por el chip azul de fondo. */
    [data-testid="stTabs"] .react-aria-SelectionIndicator {{
        display: none !important;
    }}

    /* Filas de KPI (st.columns + kpi_card_html) — todas las tarjetas de
       una misma fila (y de una página a otra) quedan a la misma altura,
       sin importar cuánto texto tenga cada valor/etiqueta. */
    [data-testid="stHorizontalBlock"] {{
        align-items: stretch !important;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
        display: flex !important;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"] > div {{
        width: 100%;
    }}
    .icesi-kpi-card:hover {{
        box-shadow: 0 4px 16px rgba(84,84,233,0.4) !important;
    }}
    </style>
    """, unsafe_allow_html=True)


def kpi_card_html(icon: str, label: str, value: str, tooltip: str = "") -> str:
    """Tarjeta de KPI con fondo degradado en Azul Icesi — estándar de KPI
    de TODA la plataforma (reemplaza a `st.metric()` nativo en todas las
    páginas), para que cualquier fila de KPIs se lea con la misma
    identidad visual sin importar la página en la que esté.

    Uso:
        st.markdown(kpi_card_html("⚡", "FNCER", "12.4 %", "..."), unsafe_allow_html=True)

    `tooltip` se muestra como tooltip nativo del navegador (atributo HTML
    title) al pasar el mouse — más simple que el ⓘ de st.metric, pero
    funciona igual sin depender de un componente de Streamlit."""
    tooltip_escaped = tooltip.replace('"', "&quot;")
    return f"""
    <div class="icesi-kpi-card" title="{tooltip_escaped}" style="
        background: linear-gradient(135deg, {ICESI_BLUE} 0%, {ICESI_BLUE_DARK} 100%);
        border-radius: 12px;
        padding: 14px 16px;
        color: white;
        height: 100%;
        min-height: 84px;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 3px 10px rgba(84,84,233,0.28);
        transition: box-shadow 0.15s ease;
        cursor: default;
        font-family: {FONT_FAMILY};
    ">
        <div style="font-size:0.74rem; font-weight:600; opacity:0.92; letter-spacing:0.2px;">
            {icon} {label}
        </div>
        <div style="font-size:1.6rem; font-weight:800; margin-top:4px; line-height:1.15;">
            {value}
        </div>
    </div>
    """
