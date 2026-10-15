"""
pages/2_Matriz_Generacion_Horaria.py

Módulo "Matriz de Generación Horaria" del Observatorio Energético SIN:
composición por tecnología de la generación horaria por recurso.

Fuente: catálogo principal de pydataxm — misma infraestructura ya validada
para reservas, sin SIMEM, sin credenciales. Usa la métrica "Gene"
(Generación Real por Recurso) — es la única vista expuesta en la UI por
ahora. "Ideal" (GeneIdea) y "Programada" (GeneProgDesp) siguen disponibles
en GENE_VISTAS (data/predespacho_xm.py) y en `fetch_generacion_raw()` por
si hacen falta para otra cosa — para volver a exponerlas acá, restaurá el
selector (`st.radio` sobre `GENE_VISTAS.keys()`) que se quitó de `render()`.
"""
import datetime as dt
import sys
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sala_control.data.predespacho_xm import (
    fetch_generacion_raw, adaptar_a_formato_ancho, parse_predespacho_file,
    fetch_listado_recursos, enriquecer_con_recursos,
    fetch_listado_agentes, nombres_de_agentes, GENE_VISTAS,
)
from sala_control.analytics.generacion_mix import (
    compute_gen_por_tipo, resumen_participacion, resumen_participacion_agente,
    etiquetas_leyenda_con_fuente, kpis_generacion,
)
from sala_control.charts.generacion_chart import build_generacion_figure, build_participacion_barchart
from sala_control.theme import apply_icesi_theme, ICESI_BLUE, ICESI_BLUE_DARK, kpi_card_html

try:
    st.set_page_config(layout="wide", page_title="Matriz de Generación Horaria")
except Exception:
    pass  # ya se llamó desde app.py (multipage) — no puede llamarse dos veces por corrida
apply_icesi_theme()


@st.cache_data(ttl=3600, show_spinner="Consultando API XM...")
def _load_generacion_con_fallback(fecha_deseada: dt.date, keywords: list[str], dias_hacia_atras: int = 7):
    """Intenta `fecha_deseada` primero; si viene vacía (rezago de
    publicación, ya confirmado que pasa con 'ayer' específicamente), trae
    una ventana más amplia hacia atrás y usa la fecha MÁS RECIENTE que sí
    tenga datos — mismo patrón que ya usamos en reservas (usar la fecha
    real más reciente, no asumir que hoy/ayer ya está publicado).

    `keywords`: cuál métrica de GENE_VISTAS usar (Ideal/Real/Programada) —
    al ser parámetro de una función con `st.cache_data`, cambiar de vista
    en el selector no reutiliza por error la caché de otra vista.

    Returns: (df_ancho, fecha_real_usada) o (None, None) si ni la ventana
    completa tiene nada.
    """
    ventana_inicio = fecha_deseada - dt.timedelta(days=dias_hacia_atras - 1)
    crudo = fetch_generacion_raw(ventana_inicio, fecha_deseada, keywords)
    if crudo is None or len(crudo) == 0:
        return None, None

    date_col = next((c for c in crudo.columns if c.lower() == "date"), None)
    if date_col is None:
        # No se pudo identificar la columna de fecha; se asume que todo
        # el crudo corresponde a fecha_deseada (mejor esfuerzo).
        return adaptar_a_formato_ancho(crudo), fecha_deseada

    fecha_mas_reciente = crudo[date_col].dt.date.max()
    return adaptar_a_formato_ancho(crudo, fecha_filtro=fecha_mas_reciente), fecha_mas_reciente


@st.cache_data(ttl=24 * 3600, show_spinner="Consultando listado de recursos (XM)...")
def _load_listado_recursos():
    """Listado estático (Agente, Tipo oficial) — cambia con poca frecuencia,
    caché de 24h para no repetir la consulta en cada corrida."""
    return fetch_listado_recursos()


@st.cache_data(ttl=24 * 3600, show_spinner="Consultando listado de agentes (XM)...")
def _load_nombres_agentes():
    """Nombre completo de cada agente (empresa) — cambia con poca
    frecuencia, caché de 24h. Si falla, la tabla de participación por
    agente muestra el código en vez del nombre (degradación aceptable)."""
    listado = fetch_listado_agentes()
    return nombres_de_agentes(listado)


VISTA_ACTIVA = "Real"  # única vista expuesta en la UI por ahora — ver nota del docstring del módulo


def render():
    st.markdown("## Matriz de Generación Horaria")

    vista = VISTA_ACTIVA
    st.caption(f"Composición por tecnología — Generación {vista} por Recurso (API XM)")

    # Filtros en la BARRA LATERAL, solo para esta página — como cada
    # página es un script independiente que st.navigation ejecuta por
    # separado, lo que se agrega a st.sidebar aquí no aparece cuando el
    # usuario está en la otra página.
    st.sidebar.markdown("#### Filtros")
    fecha_deseada = st.sidebar.date_input("Fecha a consultar", value=dt.date.today() - dt.timedelta(days=1))

    df, fecha_real = None, None
    try:
        df, fecha_real = _load_generacion_con_fallback(fecha_deseada, GENE_VISTAS[vista])
    except Exception as e:
        st.warning(f"El fetch automático falló: {e}")

    usando_respaldo_manual = False
    if df is None:
        st.info(
            f"📌 La API no devolvió datos de Generación {vista} ni en los últimos 7 días "
            f"(o el fetch falló arriba). Sube el archivo manualmente como respaldo.",
            icon="ℹ️",
        )
        uploaded = st.file_uploader("Archivo de respaldo (mismo formato del Predespacho Ideal: "
                                     "Planta + H1..H24)", type=["txt", "csv"])
        if uploaded is None:
            st.stop()
        df = parse_predespacho_file(uploaded)
        usando_respaldo_manual = True
    elif fecha_real != fecha_deseada:
        st.caption(f"⚠ No había dato publicado para {fecha_deseada} todavía — mostrando el más "
                   f"reciente disponible: {fecha_real}.")

    # Enriquecer con el listado oficial de recursos (Agente, Tipo oficial)
    # — solo tiene sentido si los datos vinieron de la API (el archivo
    # manual de respaldo no tiene forma de cruzarse de forma confiable).
    nombres = None
    if not usando_respaldo_manual:
        try:
            listado = _load_listado_recursos()
            df = enriquecer_con_recursos(df, listado)
        except Exception as e:
            st.warning(f"No se pudo cruzar con el listado de recursos: {e}. La clasificación por "
                       f"texto de respaldo NO va a funcionar bien aquí — 'Planta' en este momento "
                       f"contiene el CÓDIGO del recurso (ej. '2QBW'), no un nombre legible como "
                       f"'GUAVIO', así que los patrones de texto no van a encontrar coincidencias.")
        try:
            nombres = _load_nombres_agentes()
        except Exception:
            nombres = None

    # --- Filtro de agente (barra lateral), poblado con los que SÍ
    # participaron ese día ---
    mapa_codigo_a_nombre = {}
    if nombres is not None:
        mapa_codigo_a_nombre = dict(zip(nombres["CodigoAgente"], nombres["NombreAgente"]))

    if "Agente" in df.columns:
        codigos_presentes = sorted(df["Agente"].dropna().astype(str).str.strip().str.upper().unique())
        etiquetas_agente = {c: mapa_codigo_a_nombre.get(c, c) for c in codigos_presentes}
        opciones = ["Todos los Agentes"] + sorted(etiquetas_agente.values())
        seleccion = st.sidebar.selectbox("Agente", opciones)

        if seleccion != "Todos los Agentes":
            codigos_seleccionados = [c for c, nombre in etiquetas_agente.items() if nombre == seleccion]
            df = df[df["Agente"].astype(str).str.strip().str.upper().isin(codigos_seleccionados)]
    else:
        st.sidebar.selectbox("Agente", ["Todos los Agentes"], disabled=True,
                              help="No disponible con el archivo manual de respaldo (no trae Agente).")
        seleccion = "Todos los Agentes"

    gen_por_tipo = compute_gen_por_tipo(df)

    # ================= 4 KPIs con tarjeta temática ICESI =================
    # Mismo estilo de tarjeta (kpi_card_html) que usan todas las páginas.
    kpis = kpis_generacion(gen_por_tipo, df_enriquecido=df if not usando_respaldo_manual else None)
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(kpi_card_html(
        "🔋", "Autogeneración (AUTOG)",
        f"{kpis['autog']:.1f} %" if kpis["autog"] is not None else "Sin dato",
        "% de la generación total que es autoconsumo, fuera del despacho centralizado.",
    ), unsafe_allow_html=True)
    k2.markdown(kpi_card_html(
        "🏘️", "Gen. Distribuida (GD)",
        f"{kpis['gd']:.1f} %" if kpis["gd"] is not None else "Sin dato",
        "% de la generación total que es distribuida, a pequeña escala.",
    ), unsafe_allow_html=True)
    k3.markdown(kpi_card_html(
        "🛢️", "Térmica",
        f"{kpis['termica']:.1f} %" if kpis["termica"] is not None else "Sin dato",
        "% de combustibles fósiles. Sube cuando la hidrología aprieta — ver Riesgo Climático-Hidrológico.",
    ), unsafe_allow_html=True)
    k4.markdown(kpi_card_html(
        "🌱", "FNCER",
        f"{kpis['fncer']:.1f} %" if kpis["fncer"] is not None else "Sin dato",
        "Fuentes No Convencionales de Energía Renovable (Ley 1715): solar, eólica, biomasa, "
        "biogás, bagazo. Incluye AUTOG/GD cuyo combustible aplique.",
    ), unsafe_allow_html=True)
    st.write("")  # separador de aire entre las tarjetas y las pestañas

    # ==================== Vistas en pestañas (minimiza scroll) ====================
    # En vez de apilar el gráfico principal + 2 gráficos de participación
    # (que suman mucha altura), quedan en pestañas: solo se renderiza uno a
    # la vez, así el alto de la página queda acotado al contenido de la
    # pestaña activa, no a la suma de las tres vistas. Los títulos internos
    # de cada gráfico se quitan a propósito — el nombre de la pestaña ya
    # cumple esa función.
    # La pestaña de participación por agente solo aporta información con
    # "Todos los Agentes" seleccionado — con un agente específico filtrado,
    # su propio gráfico de participación (100% de un solo agente) no dice
    # nada nuevo.
    mostrar_tab_agente = seleccion == "Todos los Agentes"
    tab_labels = ["📊 Generación por hora", "🏭 Participación por tecnología"]
    if mostrar_tab_agente:
        tab_labels.append("🏢 Participación por agente")
    tabs = st.tabs(tab_labels)
    tab_principal, tab_tecnologia = tabs[0], tabs[1]
    tab_agente = tabs[2] if mostrar_tab_agente else None

    with tab_principal:
        etiquetas = etiquetas_leyenda_con_fuente(df) if not usando_respaldo_manual else None
        fig = build_generacion_figure(gen_por_tipo, etiquetas_leyenda=etiquetas)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with tab_tecnologia:
        # Contenedor con alto limitado y scroll propio — si hay muchas
        # categorías (o etiquetas largas), no empuja el resto de la página
        # hacia abajo, se desplaza DENTRO de esta caja.
        with st.container(height=340):
            fig_tec = build_participacion_barchart(resumen_participacion(gen_por_tipo), color=ICESI_BLUE)
            st.plotly_chart(fig_tec, width="stretch", config={"displayModeBar": False})
        if "TipoOficial" in df.columns:
            st.caption("Clasificación oficial de XM (Values_Type / Values_RecType del listado "
                       "de recursos).")
        else:
            st.caption("Clasificación por patrones de texto en el nombre del recurso, no un "
                       "catálogo oficial de XM — revisa si algo quedó mal clasificado.")

    if mostrar_tab_agente:
        with tab_agente:
            if "Agente" in df.columns:
                with st.container(height=340):
                    fig_agente = build_participacion_barchart(
                        resumen_participacion_agente(df, nombres_agentes=nombres), color=ICESI_BLUE_DARK,
                    )
                    st.plotly_chart(fig_agente, width="stretch", config={"displayModeBar": False})
                if nombres is None:
                    st.caption("No se pudo traer el listado de agentes con nombre — se muestra el "
                               "código (Values_CompanyCode). Solo se listan agentes con participación "
                               "> 0%.")
                else:
                    st.caption("Solo se listan agentes con participación > 0%.")
            else:
                st.info("No disponible — solo se puede calcular cuando los datos vienen de la API "
                        "(no del archivo manual de respaldo).")


render()
