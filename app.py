"""
app.py — Punto de entrada único del Observatorio Energético SIN.

Corre esto (no las páginas sueltas) para tener las dos páginas accesibles
desde una sola app, con navegación en la barra lateral:

    streamlit run app.py

Las páginas individuales (sala_control/pages/*.py) siguen funcionando
sueltas también (`streamlit run sala_control/pages/1_....py`), por si
necesitas depurar una en aislamiento — por eso cada una envuelve su propio
`st.set_page_config()` en un try/except (Streamlit solo permite llamarlo
una vez por corrida; si ya se llamó aquí en app.py, la página individual
lo detecta y no truena).
"""
import streamlit as st

from sala_control.theme import apply_icesi_theme, ICESI_BLUE

st.set_page_config(layout="wide", page_title="Observatorio Energético SIN", page_icon="🔭")
apply_icesi_theme()  # se llama AQUÍ (no solo dentro de cada página) para que
                      # el tema esté aplicado desde el primer render, incluida
                      # la barra lateral de navegación de st.navigation.

st.sidebar.markdown(
    f"""
    <div style="padding: 0.5rem 0 1rem 0;">
        <span style="font-size:1.3rem; font-weight:800; color:{ICESI_BLUE};">
            🔭 Observatorio Energético SIN
        </span><br>
        <span style="font-size:0.8rem; color:#898D8D;">
            Plataforma de inteligencia del mercado eléctrico
        </span>
    </div>
    <hr style="margin: 0 0 0.5rem 0; border-color: rgba(84,84,233,0.2);">
    """,
    unsafe_allow_html=True,
)

pg = st.navigation([
    st.Page(
        "sala_control/pages/1_Riesgo_Climatico_Hidrologico.py",
        title="Riesgo Climático-Hidrológico",
        icon="🌊",
    ),
    st.Page(
        "sala_control/pages/2_Matriz_Generacion_Horaria.py",
        title="Matriz de Generación Horaria",
        icon="⚡",
    ),
])
pg.run()
