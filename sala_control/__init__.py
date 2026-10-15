"""sala_control — paquete de la app "Observatorio Energético SIN".

Este módulo se ejecuta al importar CUALQUIER submódulo del paquete (tanto
desde `app.py` como desde cada página individual en modo standalone), así
que es el lugar correcto para un parche que tiene que aplicarse ANTES de
que Streamlit/Tornado abran el servidor — parchear desde `app.py` llegaría
tarde, porque el bootstrap de `streamlit run` ya creó el event loop antes
de ejecutar el script de la página.

En Windows, Tornado (el servidor que usa Streamlit) corre sobre el
`ProactorEventLoop` de asyncio. Cuando el navegador cierra o recarga la
conexión websocket de forma abrupta (recarga en caliente, cerrar pestaña),
el callback de limpieza de esa transport (`_call_connection_lost`) lanza
un `ConnectionResetError` que no afecta el funcionamiento de la app — solo
ensucia la consola con un traceback. Se sobreescribe ESE callback puntual
para tragarse específicamente ese error, dejando pasar cualquier otro.
"""
import sys

if sys.platform == "win32":
    from asyncio.proactor_events import _ProactorBasePipeTransport

    _original_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

    def _call_connection_lost_silencioso(self, exc):
        try:
            _original_call_connection_lost(self, exc)
        except ConnectionResetError:
            pass

    _ProactorBasePipeTransport._call_connection_lost = _call_connection_lost_silencioso
