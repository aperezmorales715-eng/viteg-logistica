import streamlit as st
import mysql.connector
import pandas as pd
import folium
from streamlit_folium import st_folium
import streamlit_autorefresh
import urllib.parse
from streamlit_geolocation import streamlit_geolocation
from contextlib import contextmanager
from datetime import datetime
import io
import numpy as np

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(page_title="Sistema Interno - Agua VITEG", layout="wide")

# ==========================================
# ESTILO VISUAL (tema azul tipo app de reparto)
# ==========================================
st.markdown("""
<style>
    :root {
        --viteg-azul: #1a73e8;
        --viteg-azul-claro: #EAF2FE;
        --viteg-verde: #25D366;
    }

    /* Botones generales: más redondeados, tipo "pill" */
    div.stButton > button {
        border-radius: 24px;
        font-weight: 600;
        border: 1px solid #DCEBFC;
    }
    div.stButton > button[kind="primary"] {
        background-color: var(--viteg-azul);
        border-color: var(--viteg-azul);
    }

    /* Tarjetas de métricas */
    [data-testid="stMetric"] {
        background-color: var(--viteg-azul-claro);
        border-radius: 14px;
        padding: 14px 10px;
        border: 1px solid #DCEBFC;
    }
    [data-testid="stMetricLabel"] {
        font-weight: 600;
    }

    /* Pedidos como tarjetas (expanders) */
    [data-testid="stExpander"] {
        border-radius: 14px;
        border: 1px solid #E3ECF5;
        margin-bottom: 10px;
        overflow: hidden;
    }
    [data-testid="stExpander"] summary {
        font-weight: 600;
        padding: 10px 6px;
    }

    /* Inputs y selects redondeados */
    div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input, .stTextArea textarea {
        border-radius: 10px !important;
    }

    /* Barra de progreso */
    .stProgress > div > div > div {
        background-color: var(--viteg-azul);
    }

    /* Separadores más sutiles */
    hr {
        margin: 0.6rem 0;
        opacity: 0.25;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# LOGIN
# ==========================================
CLAVE_ADMIN = st.secrets.get("CLAVE_ADMIN", "viteg2024")
CLAVE_REPARTIDOR = st.secrets.get("CLAVE_REPARTIDOR", "reparto123")

if "rol" not in st.session_state:
    st.session_state.rol = None

if st.session_state.rol is None:
    st.image("logo.jpeg", width=300)
    st.title("🏭 Agua VITEG — Acceso al Sistema")
    st.markdown("Ingresa tu clave para continuar.")
    clave = st.text_input("🔑 Contraseña:", type="password")
    if st.button("Entrar", use_container_width=True, type="primary"):
        if clave == CLAVE_ADMIN:
            st.session_state.rol = "admin"
            st.rerun()
        elif clave == CLAVE_REPARTIDOR:
            st.session_state.rol = "repartidor"
            st.rerun()
        else:
            st.error("❌ Contraseña incorrecta.")
    st.stop()

# ==========================================
# CONEXIÓN A BD
# ==========================================
@contextmanager
def get_db():
    db = None
    try:
        db = mysql.connector.connect(
            host=st.secrets["DB_HOST"],
            user=st.secrets["DB_USER"],
            password=st.secrets["DB_PASSWORD"],
            database=st.secrets["DB_NAME"],
            port=int(st.secrets["DB_PORT"])
        )
        yield db
    except mysql.connector.Error as e:
        st.error(f"❌ Error de conexión: {e}")
        yield None
    finally:
        if db and db.is_connected():
            db.close()

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def reiniciar_ruta_completa(nombre_ruta):
    with get_db() as db:
        if db:
            try:
                cursor = db.cursor()
                cursor.execute("UPDATE pedidos SET estatus = 'pendiente' WHERE ruta = %s", (nombre_ruta,))
                db.commit()
                cursor.close()
                return True
            except Exception as e:
                st.error(f"Error al reiniciar ruta: {e}")
    return False

def enviar_whatsapp_link(telefono, mensaje):
    tel = str(telefono).strip()
    if not tel.startswith("52"):
        tel = f"52{tel}"
    return f"https://wa.me/{tel}?text={urllib.parse.quote(mensaje)}"

def extraer_foto_y_texto(referencia):
    """Si el texto de referencia contiene un link (http/https), lo separa del resto.
    Así el campo 'Referencias' puede seguir usándose como texto normal, pero si
    alguien pega un link a una foto (Google Fotos, Drive, etc.), la app la detecta
    y la muestra como imagen — sin necesidad de una columna nueva en la BD."""
    if not referencia:
        return "", None
    import re
    match = re.search(r'(https?://\S+)', str(referencia))
    if match:
        url = match.group(1)
        texto_limpio = str(referencia).replace(url, "").strip(" -,.:;")
        return texto_limpio, url
    return referencia, None

def exportar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Pedidos')
    return output.getvalue()

def optimizar_ruta(df):
    df = df.reset_index(drop=True)
    coords = df[['latitud', 'longitud']].values
    n = len(coords)
    if n <= 1:
        return df
    coords = coords.astype(float)
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    dist_matrix = np.sqrt((diff ** 2).sum(axis=2))
    visitado = [False] * n
    orden = []
    actual = 0
    for _ in range(n):
        visitado[actual] = True
        orden.append(actual)
        distancias = dist_matrix[actual].copy()
        distancias[visitado] = np.inf
        siguiente = int(np.argmin(distancias))
        actual = siguiente
    return df.iloc[orden].reset_index(drop=True)

# ==========================================
# DIÁLOGOS
# ==========================================
@st.dialog("🚪 Cerrar sesión")
def dialogo_cerrar_sesion():
    st.warning("¿Estás seguro que deseas cerrar sesión?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, cerrar sesión", type="primary", use_container_width=True):
            st.session_state.rol = None
            st.session_state.nav_actual = None
            st.rerun()
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

@st.dialog("⚠️ Confirmar reinicio de TODAS las rutas")
def dialogo_reiniciar_todo():
    st.error("Esta acción marcará TODOS los pedidos como 'pendiente'. No se puede deshacer.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, reiniciar todo", type="primary", use_container_width=True):
            with get_db() as db:
                if db:
                    cursor = db.cursor()
                    cursor.execute("UPDATE pedidos SET estatus = 'pendiente'")
                    db.commit()
                    cursor.close()
            st.rerun()
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

@st.dialog("⚠️ Confirmar reinicio de ruta")
def dialogo_reiniciar_ruta(nombre_ruta):
    st.error(f"Esta acción marcará todos los pedidos de **'{nombre_ruta}'** como 'pendiente'.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, reiniciar", type="primary", use_container_width=True):
            reiniciar_ruta_completa(nombre_ruta)
            st.rerun()
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

@st.dialog("🗑️ Confirmar eliminación de cliente")
def dialogo_eliminar_cliente(id_cliente, nombre_cliente):
    st.error(f"¿Eliminar permanentemente a **{nombre_cliente}**? Esta acción no se puede deshacer.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, eliminar", type="primary", use_container_width=True):
            with get_db() as db:
                if db:
                    cursor = db.cursor()
                    cursor.execute("DELETE FROM pedidos WHERE id = %s", (id_cliente,))
                    db.commit()
                    cursor.close()
            st.rerun()
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

# ==========================================
# ESTADOS DE SESIÓN
# ==========================================
defaults = {
    "ultimo_conteo_pedidos": 0,
    "id_max_previo": 0,
    "id_cliente_editar": None,
    "alerta_pendiente": False,
    "detalles_nuevo_pedido": {},
    "ruta_optimizada": False,
    "ruta_sel_previa": None,
    "df_ruta_ordenada": None,
    "orden_manual": None,
    "modo_reordenar": False,
    "lista_ids_manual": [],
    "lista_ids_ruta": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.image("logo.jpeg", use_column_width=True)
    st.markdown("---")
    rol_label = "👔 Administrador" if st.session_state.rol == "admin" else "🚚 Repartidor"
    st.markdown(f"**{rol_label}**")
    st.markdown(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    st.markdown("---")
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        dialogo_cerrar_sesion()

# ==========================================
# TÍTULO
# ==========================================
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    st.image("logo.jpeg", width=120)
with col_titulo:
    st.title("🏭 Sistema de Gestión Logística - Embotelladora Agua VITEG")
    st.markdown("Panel de control interno para el monitoreo de rutas, despacho de repartidores y análisis de demanda.")

# ==========================================
# NAVEGACIÓN (botones tipo pill — más visual y táctil en celular)
# ==========================================
SECCIONES_ADMIN = ["📍 Mapa", "🚚 Panel Chofer", "📝 Registro", "📲 Preventa", "📊 Administrador", "📈 Reportes"]
SECCIONES_REP = ["🚚 Mi Ruta", "📝 Registrar", "📲 Preventa"]

if st.session_state.get("nav_actual") is None:
    st.session_state.nav_actual = SECCIONES_ADMIN[0] if st.session_state.rol == "admin" else SECCIONES_REP[0]

opciones_nav = SECCIONES_ADMIN if st.session_state.rol == "admin" else SECCIONES_REP

# Auto-reparación: si nav_actual quedó apuntando a una sección que no existe
# en el menú del rol actual (ej. se cerró sesión de admin y se entró como
# repartidor sin recargar la página), se reinicia al primer botón válido
# en vez de tronar con KeyError.
if st.session_state.nav_actual not in opciones_nav:
    st.session_state.nav_actual = opciones_nav[0]

cols_nav = st.columns(3)
for i, op in enumerate(opciones_nav):
    with cols_nav[i % 3]:
        es_actual = st.session_state.nav_actual == op
        if st.button(op, key=f"navbtn_{op}", use_container_width=True, type="primary" if es_actual else "secondary"):
            st.session_state.nav_actual = op
            st.rerun()

if st.session_state.rol == "admin":
    seccion = st.session_state.nav_actual
else:
    # Los nombres cortos del menú se mapean a los nombres completos usados en el resto del código
    _mapa_rep = {
        "🚚 Mi Ruta": "🚚 Mi Ruta de Entrega",
        "📝 Registrar": "📝 Registrar Cliente",
        "📲 Preventa": "📲 Notificaciones de Preventa",
    }
    seccion_rep = _mapa_rep[st.session_state.nav_actual]
st.divider()

# ==========================================
# DETECCIÓN DE NUEVOS PEDIDOS
# ==========================================
with get_db() as db_alertas:
    if db_alertas:
        try:
            cursor_conteo = db_alertas.cursor()
            cursor_conteo.execute("SELECT COUNT(id), MAX(id) FROM pedidos")
            total_actual, id_max_actual = cursor_conteo.fetchone()
            total_actual = total_actual or 0
            id_max_actual = id_max_actual or 0
            if st.session_state.ultimo_conteo_pedidos == 0:
                st.session_state.ultimo_conteo_pedidos = total_actual
                st.session_state.id_max_previo = id_max_actual
            if total_actual > st.session_state.ultimo_conteo_pedidos or id_max_actual > st.session_state.id_max_previo:
                df_nuevo = pd.read_sql("SELECT nombre_cliente, ruta, referencia FROM pedidos ORDER BY id DESC LIMIT 1", db_alertas)
                if not df_nuevo.empty:
                    p = df_nuevo.iloc[0]
                    st.session_state.detalles_nuevo_pedido = {
                        "cliente": p['nombre_cliente'],
                        "ruta": p['ruta'] or "Sin Ruta",
                        "referencia": p['referencia'] or "Sin referencias"
                    }
                    st.session_state.alerta_pendiente = True
                st.session_state.ultimo_conteo_pedidos = total_actual
                st.session_state.id_max_previo = id_max_actual
            elif total_actual < st.session_state.ultimo_conteo_pedidos:
                st.session_state.ultimo_conteo_pedidos = total_actual
                st.session_state.id_max_previo = id_max_actual
        except Exception as e:
            st.error(f"Error en alertas: {e}")

if st.session_state.alerta_pendiente:
    d = st.session_state.detalles_nuevo_pedido
    st.error(f"🚨 ¡NUEVO PEDIDO! | Cliente: {d.get('cliente')} | Ruta: {d.get('ruta')} | Ref: {d.get('referencia')}")
    if st.button("Confirmar lectura y limpiar alerta", key="btn_limpiar_alerta_global", use_container_width=True):
        st.session_state.alerta_pendiente = False
        st.rerun()
    st.divider()

# ==========================================
# RENDERIZADO SEGÚN ROL
# ==========================================
if st.session_state.rol == "admin":

    # --- MAPA ---
    if seccion == "📍 Mapa":
        st.subheader("🗺️ Monitoreo Geográfico de Pedidos")
        streamlit_autorefresh.st_autorefresh(interval=20000, key="mapa_refresh")
        with get_db() as db:
            if db:
                try:
                    df_mapa_todo = pd.read_sql("SELECT * FROM pedidos WHERE latitud != 0 AND longitud != 0", db)
                    if not df_mapa_todo.empty:
                        df_mapa_todo['latitud'] = pd.to_numeric(df_mapa_todo['latitud'], errors='coerce')
                        df_mapa_todo['longitud'] = pd.to_numeric(df_mapa_todo['longitud'], errors='coerce')
                        df_mapa_todo = df_mapa_todo.dropna(subset=['latitud', 'longitud'])
                    if not df_mapa_todo.empty:
                        col_f1, col_f2 = st.columns(2)
                        with col_f1:
                            rutas_disponibles = ["Todas"] + sorted(df_mapa_todo['ruta'].dropna().unique().tolist())
                            filtro_ruta = st.selectbox("🗂️ Filtrar por ruta:", rutas_disponibles, key="map_ruta_filter")
                        with col_f2:
                            filtro_estatus = st.selectbox("📌 Filtrar por estatus:", ["Todos", "Pendientes", "Entregados", "No Encontrados"], key="map_estatus_filter")
                        df_mapa = df_mapa_todo.copy()
                        if filtro_ruta != "Todas":
                            df_mapa = df_mapa[df_mapa['ruta'] == filtro_ruta]
                        mapa_filtros = {"Pendientes": "pendiente", "Entregados": "entregado", "No Encontrados": "no encontrado"}
                        df_filtrado = df_mapa[df_mapa['estatus'] == mapa_filtros[filtro_estatus]] if filtro_estatus in mapa_filtros else df_mapa
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Total visibles", len(df_mapa))
                        c2.metric("⏳ Pendientes", len(df_mapa[df_mapa['estatus'] == 'pendiente']))
                        c3.metric("✅ Entregados", len(df_mapa[df_mapa['estatus'] == 'entregado']))
                        c4.metric("❌ No encontrados", len(df_mapa[df_mapa['estatus'] == 'no encontrado']))
                        if not df_filtrado.empty and df_filtrado['latitud'].notna().any():
                            centro_lat = df_filtrado['latitud'].mean()
                            centro_lon = df_filtrado['longitud'].mean()
                            if pd.isna(centro_lat) or pd.isna(centro_lon) or (centro_lat == 0 and centro_lon == 0):
                                centro_lat, centro_lon = 19.3150, -98.2400
                        else:
                            centro_lat, centro_lon = 19.3150, -98.2400
                        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=14 if filtro_ruta != "Todas" else 13)
                        colores = {"pendiente": ("red", "info-sign"), "no encontrado": ("orange", "remove-sign")}
                        for _, row in df_filtrado.iterrows():
                            color, icono = colores.get(row['estatus'], ("green", "ok-sign"))
                            url_gmaps = f"https://www.google.com/maps/search/?api=1&query={row['latitud']},{row['longitud']}"
                            popup_text = f"<b>Cliente:</b> {row['nombre_cliente']}<br><b>Zona:</b> {row['ruta']}<br><b>Estatus:</b> {row['estatus'].upper()}<br><a href='{url_gmaps}' target='_blank'>📍 Ver en Google Maps</a>"
                            folium.Marker(location=[row['latitud'], row['longitud']], popup=folium.Popup(popup_text, max_width=300), icon=folium.Icon(color=color, icon=icono)).add_to(m)
                        st_folium(m, width=1200, height=500, returned_objects=[])
                    else:
                        st.info("No hay pedidos con coordenadas registradas.")
                except Exception as e:
                    st.error(f"Error al cargar el mapa: {e}")

    # --- PANEL CHOFER (admin) ---
    if seccion == "🚚 Panel Chofer":
        st.subheader("🚚 Panel del Chofer")
        with get_db() as db:
            if db:
                try:
                    df_chofer = pd.read_sql("SELECT id, nombre_cliente, telefono, ruta, cantidad_20L, cantidad_10L, referencia, estatus, latitud, longitud FROM pedidos WHERE estatus != 'entregado'", db)
                    if not df_chofer.empty:
                        rutas_chofer = sorted(list(df_chofer['ruta'].unique()))
                        ruta_sel = st.selectbox("Selecciona tu Ruta / Zona:", rutas_chofer, key="chofer_ruta_sel_admin")
                        if st.session_state.ruta_sel_previa != ruta_sel:
                            st.session_state.ruta_optimizada = False
                            st.session_state.df_ruta_ordenada = None
                            st.session_state.orden_manual = None
                            st.session_state.modo_reordenar = False
                            st.session_state.ruta_sel_previa = ruta_sel
                        df_ruta_base = df_chofer[df_chofer['ruta'] == ruta_sel].copy()
                        total_ruta = len(df_ruta_base)
                        with get_db() as db2:
                            if db2:
                                df_todos = pd.read_sql("SELECT estatus FROM pedidos WHERE ruta = %s", db2, params=(ruta_sel,))
                                entregados_hoy = len(df_todos[df_todos['estatus'] == 'entregado'])
                                total_ruta_completa = len(df_todos)
                        c1, c2, c3 = st.columns(3)
                        c1.metric("📦 Pendientes", total_ruta)
                        c2.metric("✅ Entregados", entregados_hoy)
                        progreso = int((entregados_hoy / total_ruta_completa) * 100) if total_ruta_completa > 0 else 0
                        c3.metric("📊 Progreso", f"{progreso}%")
                        st.progress(progreso / 100)
                        st.divider()
                        coords_validas = df_ruta_base[(df_ruta_base['latitud'] != 0) & (df_ruta_base['longitud'] != 0)].copy()
                        sin_coords = df_ruta_base[(df_ruta_base['latitud'] == 0) | (df_ruta_base['longitud'] == 0)].copy()
                        col_opt1, col_opt2, col_opt3 = st.columns(3)
                        with col_opt1:
                            btn_optimizar = st.button("🧭 OPTIMIZAR CON IA", use_container_width=True, type="primary", key="opt_admin")
                        with col_opt2:
                            btn_reordenar = st.button("✋ AJUSTAR MANUALMENTE", use_container_width=True, key="rea_admin")
                        with col_opt3:
                            btn_original = st.button("↩️ Orden original", use_container_width=True, key="ori_admin")
                        if btn_optimizar:
                            if len(coords_validas) >= 2:
                                df_optimizado = pd.concat([optimizar_ruta(coords_validas), sin_coords]).reset_index(drop=True)
                                st.session_state.df_ruta_ordenada = df_optimizado
                                st.session_state.orden_manual = None
                                st.session_state.ruta_optimizada = True
                                st.session_state.modo_reordenar = False
                            else:
                                st.warning("⚠️ Se necesitan al menos 2 clientes con GPS para optimizar.")
                        if btn_reordenar:
                            st.session_state.modo_reordenar = True
                        if btn_original:
                            st.session_state.ruta_optimizada = False
                            st.session_state.df_ruta_ordenada = None
                            st.session_state.orden_manual = None
                            st.session_state.modo_reordenar = False
                        if st.session_state.ruta_optimizada and st.session_state.df_ruta_ordenada is not None:
                            df_ruta_actual = st.session_state.df_ruta_ordenada.copy()
                            st.success("✅ Ruta optimizada por IA.")
                        elif st.session_state.orden_manual is not None:
                            df_ruta_actual = st.session_state.orden_manual.copy()
                            st.success("✅ Orden ajustado manualmente.")
                        else:
                            df_ruta_actual = df_ruta_base.copy()
                        if st.session_state.modo_reordenar:
                            st.markdown("### ✋ Ajusta el orden manualmente")
                            if "lista_ids_manual" not in st.session_state or st.session_state.lista_ids_ruta != ruta_sel:
                                st.session_state.lista_ids_manual = list(df_ruta_actual['id'])
                                st.session_state.lista_ids_ruta = ruta_sel
                            ids_orden = st.session_state.lista_ids_manual
                            df_orden = df_ruta_actual.set_index('id').loc[ids_orden].reset_index()
                            for i, (_, row) in enumerate(df_orden.iterrows()):
                                col_n, col_u, col_d = st.columns([6, 1, 1])
                                col_n.write(f"**#{i+1}** — {row['nombre_cliente']}")
                                if i > 0:
                                    if col_u.button("⬆️", key=f"up_a_{row['id']}_{i}"):
                                        ids_orden[i], ids_orden[i-1] = ids_orden[i-1], ids_orden[i]
                                        st.session_state.lista_ids_manual = ids_orden
                                        st.rerun()
                                if i < len(df_orden) - 1:
                                    if col_d.button("⬇️", key=f"dn_a_{row['id']}_{i}"):
                                        ids_orden[i], ids_orden[i+1] = ids_orden[i+1], ids_orden[i]
                                        st.session_state.lista_ids_manual = ids_orden
                                        st.rerun()
                            if st.button("✅ Confirmar orden", type="primary", use_container_width=True, key="conf_admin"):
                                df_manual = df_ruta_actual.set_index('id').loc[st.session_state.lista_ids_manual].reset_index()
                                st.session_state.orden_manual = df_manual
                                st.session_state.ruta_optimizada = False
                                st.session_state.modo_reordenar = False
                                st.rerun()
                            st.divider()
                        df_maps = df_ruta_actual[(df_ruta_actual['latitud'] != 0) & (df_ruta_actual['longitud'] != 0)]
                        if len(df_maps) > 1:
                            origen = f"{df_maps.iloc[0]['latitud']},{df_maps.iloc[0]['longitud']}"
                            destino = f"{df_maps.iloc[-1]['latitud']},{df_maps.iloc[-1]['longitud']}"
                            url_ruta_completa = f"https://www.google.com/maps/dir/{origen}/{destino}"
                            label = "🗺️ VER RUTA OPTIMIZADA" if st.session_state.ruta_optimizada else "🗺️ VER RUTA COMPLETA"
                            st.markdown(f'<a href="{url_ruta_completa}" target="_blank"><button style="background-color:#34A853;color:white;border:none;padding:12px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;font-size:15px;margin-bottom:10px;">{label}</button></a>', unsafe_allow_html=True)
                        st.divider()
                        titulo_lista = "🧭 Orden optimizado" if st.session_state.ruta_optimizada else "📋 Pedidos activos"
                        st.markdown(f"### {titulo_lista}: {ruta_sel} ({total_ruta} restantes)")
                        for idx, (_, row) in enumerate(df_ruta_actual.iterrows(), start=1):
                            num_tel = str(row['telefono']).strip() if row['telefono'] else "S/N"
                            prefix_icon = "⏳" if row['estatus'] == 'pendiente' else "❌"
                            num_parada = f"#{idx} — " if st.session_state.ruta_optimizada else ""
                            with st.expander(f"{prefix_icon} {num_parada}{row['nombre_cliente']} | {num_tel}"):
                                st.write(f"🛒 {row['cantidad_20L']} Garrafones 20L | {row['cantidad_10L']} Garrafones 10L")
                                texto_ref, foto_url = extraer_foto_y_texto(row['referencia'])
                                st.write(f"🏠 Referencias: {texto_ref if texto_ref else 'Sin notas'}")
                                if foto_url:
                                    st.markdown(f'<a href="{foto_url}" target="_blank">📷 Ver foto de referencia</a>', unsafe_allow_html=True)
                                    try:
                                        st.image(foto_url, width=250)
                                    except Exception:
                                        pass
                                if row['latitud'] != 0 and row['longitud'] != 0:
                                    url_gmaps = f"https://www.google.com/maps/search/?api=1&query={row['latitud']},{row['longitud']}"
                                    st.markdown(f'<a href="{url_gmaps}" target="_blank"><button style="background-color:#1a73e8;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">🗺️ NAVEGAR</button></a>', unsafe_allow_html=True)
                                if num_tel != "S/N" and len(num_tel) >= 10:
                                    c1, c2, c3 = st.columns(3)
                                    with c1:
                                        st.markdown(f'<a href="tel:{num_tel}"><button style="background-color:#007BFF;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">📞 LLAMAR</button></a>', unsafe_allow_html=True)
                                    with c2:
                                        msg_afuera = "Hola, le avisamos de Agua VITEG 💧. El camión ya está afuera. ¡Gracias!"
                                        st.markdown(f'<a href="{enviar_whatsapp_link(num_tel, msg_afuera)}" target="_blank"><button style="background-color:#25D366;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">📲 YA ESTOY AFUERA</button></a>', unsafe_allow_html=True)
                                    with c3:
                                        msg_ent = f"Hola {row['nombre_cliente']}, su pedido de Agua VITEG 💧 fue entregado. ¡Gracias!"
                                        st.markdown(f'<a href="{enviar_whatsapp_link(num_tel, msg_ent)}" target="_blank"><button style="background-color:#128C7E;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">✅ CONFIRMAR</button></a>', unsafe_allow_html=True)
                                st.markdown("---")
                                col_e1, col_e2 = st.columns(2)
                                with col_e1:
                                    if st.button("✅ Marcar Entregado", key=f"ent_a_{row['id']}"):
                                        cursor = db.cursor()
                                        cursor.execute("UPDATE pedidos SET estatus = 'entregado' WHERE id = %s", (row['id'],))
                                        db.commit()
                                        cursor.close()
                                        st.session_state.ruta_optimizada = False
                                        st.session_state.df_ruta_ordenada = None
                                        st.rerun()
                                with col_e2:
                                    if row['estatus'] != 'no encontrado':
                                        if st.button("❌ No Encontrado", key=f"noe_a_{row['id']}"):
                                            cursor = db.cursor()
                                            cursor.execute("UPDATE pedidos SET estatus = 'no encontrado' WHERE id = %s", (row['id'],))
                                            db.commit()
                                            cursor.close()
                                            st.rerun()
                    else:
                        st.success("🚚 No hay pedidos pendientes.")
                except Exception as e:
                    st.error(f"Error: {e}")

    # --- REGISTRO ---
    if seccion == "📝 Registro":
        st.subheader("📝 Registro de Pedidos")
        opciones_rutas = ["-- Escribir nueva ruta --"]
        with get_db() as db_rutas:
            if db_rutas:
                cursor_r = db_rutas.cursor()
                cursor_r.execute("SELECT DISTINCT ruta FROM pedidos WHERE ruta IS NOT NULL AND ruta != ''")
                for row_r in cursor_r.fetchall():
                    if row_r[0] not in opciones_rutas:
                        opciones_rutas.append(row_r[0])
                cursor_r.close()
        st.markdown("### 🔍 Buscador de Clientes")
        busqueda = st.text_input("Buscar por nombre o teléfono:", key="busqueda_admin")
        if busqueda:
            with get_db() as db_bus:
                if db_bus:
                    df_bus = pd.read_sql("SELECT id, nombre_cliente, telefono, ruta, referencia, estatus FROM pedidos WHERE nombre_cliente LIKE %s OR telefono LIKE %s", db_bus, params=(f"%{busqueda}%", f"%{busqueda}%"))
                    if not df_bus.empty:
                        st.dataframe(df_bus, use_container_width=True)
                    else:
                        st.info("No se encontraron resultados.")
        st.divider()
        st.markdown("### ➕ Nuevo Cliente / Pedido")
        location = streamlit_geolocation()
        lat_val, lon_val = 0.0, 0.0
        if location and isinstance(location, dict) and location.get("latitude") is not None:
            lat_val = float(location["latitude"])
            lon_val = float(location["longitude"])
        with st.form("alta_admin", clear_on_submit=True):
            col_form1, col_form2 = st.columns(2)
            with col_form1:
                nom = st.text_input("Nombre completo del Cliente:*")
                tel = st.text_input("Teléfono Celular:")
                sel_ruta = st.selectbox("Ruta:", opciones_rutas)
                rut = st.text_input("Nueva ruta:") if sel_ruta == "-- Escribir nueva ruta --" else sel_ruta
                cant_20 = st.number_input("Garrafones 20L:", min_value=0, value=0)
                cant_10 = st.number_input("Garrafones 10L:", min_value=0, value=0)
            with col_form2:
                lat_f = st.number_input("Latitud:", value=lat_val, format="%.6f")
                lon_f = st.number_input("Longitud:", value=lon_val, format="%.6f")
                ref = st.text_input("Referencias del domicilio:", help="📷 Tip: puedes pegar aquí un link a una foto de la fachada (súbela a Google Fotos/Drive, comparte el link público, y pégalo junto al texto). La app la mostrará como imagen para el repartidor.")
            if st.form_submit_button("💾 Guardar y Registrar", use_container_width=True):
                if nom and rut and rut.strip():
                    with get_db() as db_alta:
                        if db_alta:
                            try:
                                cursor_a = db_alta.cursor()
                                cursor_a.execute("INSERT INTO pedidos (nombre_cliente, telefono, ruta, cantidad_20L, cantidad_10L, referencia, estatus, latitud, longitud, direccion) VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', %s, %s, '')", (nom, tel, rut, cant_20, cant_10, ref, lat_f, lon_f))
                                db_alta.commit()
                                cursor_a.close()
                                st.success(f"🎉 Cliente '{nom}' registrado en ruta: {rut}")
                                if tel and len(str(tel).strip()) >= 10:
                                    msg_conf = f"Hola {nom}, su pedido de Agua VITEG 💧 fue registrado. ¡Gracias!"
                                    st.markdown(f'<a href="{enviar_whatsapp_link(tel, msg_conf)}" target="_blank"><button style="background-color:#25D366;color:white;border:none;padding:10px;border-radius:5px;cursor:pointer;font-weight:bold;">📲 Enviar confirmación</button></a>', unsafe_allow_html=True)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al registrar: {e}")
                else:
                    st.error("Completa los campos obligatorios: Nombre y Ruta.")

    # --- PREVENTA ---
    if seccion == "📲 Preventa":
        st.subheader("📲 Notificaciones y Preventa")
        plantilla_preventa = st.text_area("Plantilla de recordatorio (usa {nombre} y {ruta}):", value="Hola {nombre}, le escribimos de Agua VITEG 💧. Le recordamos que mañana el camión pasará por su zona ({ruta}). ¡Nos vemos pronto!", height=80)
        plantilla_pedido_listo = st.text_area("Plantilla de pedido listo:", value="Hola {nombre}, su pedido de Agua VITEG 💧 está listo y en camino. ¡Gracias!", height=80)
        st.divider()
        with get_db() as db:
            if db:
                try:
                    df_notif = pd.read_sql("SELECT nombre_cliente, telefono, ruta FROM pedidos", db)
                    if not df_notif.empty:
                        rutas_notif = sorted([r.strip() for r in df_notif['ruta'].unique() if r])
                        ruta_notif_sel = st.selectbox("Seleccionar Ruta:", rutas_notif, key="ruta_prev_admin")
                        df_clientes_ruta = df_notif[df_notif['ruta'] == ruta_notif_sel]
                        st.markdown(f"**{len(df_clientes_ruta)} clientes en esta ruta**")
                        st.divider()
                        for _, row_c in df_clientes_ruta.iterrows():
                            nombre = row_c['nombre_cliente']
                            telefono = str(row_c['telefono']).strip() if row_c['telefono'] else ""
                            if telefono and len(telefono) >= 10:
                                msg_prev = plantilla_preventa.replace("{nombre}", nombre).replace("{ruta}", ruta_notif_sel)
                                msg_listo = plantilla_pedido_listo.replace("{nombre}", nombre).replace("{ruta}", ruta_notif_sel)
                                col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
                                col_c1.write(f"👤 {nombre} ({telefono})")
                                col_c2.markdown(f'<a href="{enviar_whatsapp_link(telefono, msg_prev)}" target="_blank">📅 Recordatorio</a>', unsafe_allow_html=True)
                                col_c3.markdown(f'<a href="{enviar_whatsapp_link(telefono, msg_listo)}" target="_blank">📦 Listo</a>', unsafe_allow_html=True)
                            else:
                                st.warning(f"⚠️ {nombre} — sin teléfono válido.")
                except Exception as e:
                    st.error(f"Error en preventa: {e}")

    # --- ADMINISTRADOR ---
    if seccion == "📊 Administrador":
        st.subheader("📊 Panel Administrador")
        streamlit_autorefresh.st_autorefresh(interval=15000, key="datarefresh")
        with get_db() as db:
            if db:
                try:
                    df_base = pd.read_sql("SELECT * FROM pedidos", db)
                    if not df_base.empty:
                        r_disp = sorted([r for r in df_base['ruta'].unique() if r and r != 'None'])
                        sel_admin = st.selectbox("Filtrar por Ruta:", ["🌍 Todo"] + r_disp)
                        df_admin = df_base.copy() if sel_admin == "🌍 Todo" else df_base[df_base['ruta'] == sel_admin.strip()].copy()
                        st.markdown("### ✏️ Editar Cliente")
                        lista_clientes_edit = df_base.sort_values(by="nombre_cliente")
                        opciones_clientes = {row['id']: f"{row['nombre_cliente']} ({row['ruta']})" for _, row in lista_clientes_edit.iterrows()}
                        id_seleccionado = st.selectbox("Cliente a editar:", options=list(opciones_clientes.keys()), format_func=lambda x: opciones_clientes[x])
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("🔍 Cargar para Edición"):
                                st.session_state.id_cliente_editar = id_seleccionado
                        with col_btn2:
                            if st.button("🗑️ Eliminar Cliente", type="secondary"):
                                datos_elim = df_base[df_base['id'] == id_seleccionado].iloc[0]
                                dialogo_eliminar_cliente(id_seleccionado, datos_elim['nombre_cliente'])
                        if st.session_state.id_cliente_editar:
                            datos_c = df_base[df_base['id'] == st.session_state.id_cliente_editar].iloc[0]
                            with st.form("formulario_edicion_cliente"):
                                nuevo_nombre = st.text_input("Nombre:", value=datos_c['nombre_cliente'])
                                nuevo_telefono = st.text_input("Teléfono:", value=datos_c['telefono'])
                                nueva_ruta = st.text_input("Ruta:", value=datos_c['ruta'])
                                nueva_referencia = st.text_input("Referencias:", value=datos_c['referencia'], help="📷 Puedes incluir un link a una foto de la fachada aquí junto al texto.")
                                nueva_cant_20 = st.number_input("Garrafones 20L:", min_value=0, value=int(datos_c['cantidad_20L']))
                                nueva_cant_10 = st.number_input("Garrafones 10L:", min_value=0, value=int(datos_c['cantidad_10L']))
                                if st.form_submit_button("💾 Guardar Cambios"):
                                    cursor_up = db.cursor()
                                    cursor_up.execute("UPDATE pedidos SET nombre_cliente=%s, telefono=%s, ruta=%s, referencia=%s, cantidad_20L=%s, cantidad_10L=%s WHERE id=%s", (nuevo_nombre, nuevo_telefono, nueva_ruta, nueva_referencia, nueva_cant_20, nueva_cant_10, st.session_state.id_cliente_editar))
                                    db.commit()
                                    cursor_up.close()
                                    st.success("✅ Datos actualizados.")
                                    st.session_state.id_cliente_editar = None
                                    st.rerun()
                        st.divider()
                        st.markdown("### 🔁 Reinicio de Rutas")
                        st.warning("⚠️ Úsala sólo al iniciar un nuevo día de reparto.")
                        if st.button("🚨 REINICIAR TODAS LAS RUTAS", use_container_width=True):
                            dialogo_reiniciar_todo()
                        st.markdown("---")
                        ruta_a_reiniciar = st.selectbox("Reiniciar una sola ruta:", ["-- Seleccionar --"] + r_disp, key="ruta_reinicio_individual")
                        if ruta_a_reiniciar != "-- Seleccionar --":
                            if st.button(f"🔄 Reiniciar: {ruta_a_reiniciar}", use_container_width=True):
                                dialogo_reiniciar_ruta(ruta_a_reiniciar)
                        st.divider()
                        st.markdown("### 📋 Tabla de Pedidos")
                        st.dataframe(df_admin, use_container_width=True)
                        excel_data = exportar_excel(df_admin)
                        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                        st.download_button(label="📥 Exportar a Excel", data=excel_data, file_name=f"pedidos_viteg_{fecha_hoy}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                except Exception as e:
                    st.error(f"Error en panel administrador: {e}")

    # --- REPORTES ---
    if seccion == "📈 Reportes":
        st.subheader("📈 Reportes y Análisis")
        with get_db() as db:
            if db:
                try:
                    df_rep = pd.read_sql("SELECT * FROM pedidos", db)
                    if not df_rep.empty:
                        total_20 = df_rep['cantidad_20L'].sum()
                        total_10 = df_rep['cantidad_10L'].sum()
                        total_clientes = len(df_rep)
                        entregados = len(df_rep[df_rep['estatus'] == 'entregado'])
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("👥 Total Clientes", total_clientes)
                        c2.metric("💧 Garrafones 20L", int(total_20))
                        c3.metric("💧 Garrafones 10L", int(total_10))
                        c4.metric("✅ Tasa de entrega", f"{int((entregados/total_clientes)*100)}%" if total_clientes > 0 else "0%")
                        st.divider()
                        df_por_ruta = df_rep.groupby('ruta').agg(Clientes=('id', 'count'), Garrafones_20L=('cantidad_20L', 'sum'), Garrafones_10L=('cantidad_10L', 'sum'), Entregados=('estatus', lambda x: (x == 'entregado').sum()), Pendientes=('estatus', lambda x: (x == 'pendiente').sum()), No_encontrados=('estatus', lambda x: (x == 'no encontrado').sum())).reset_index()
                        st.dataframe(df_por_ruta, use_container_width=True)
                        col_g1, col_g2 = st.columns(2)
                        with col_g1:
                            st.bar_chart(df_por_ruta.set_index('ruta')['Clientes'])
                        with col_g2:
                            st.bar_chart(df_por_ruta.set_index('ruta')['Garrafones_20L'])
                        st.divider()

                        # --- VENTAS ENTREGADAS POR REPARTIDOR (usando la Ruta como identificador) ---
                        st.markdown("### 🚴 Garrafones entregados por Repartidor")
                        st.caption("Se calcula usando el nombre de la **Ruta** como identificador del repartidor. Si nombras tus rutas con el nombre de cada persona (ej. 'Ruta Juan', 'Ruta María'), esta tabla te da el total exacto por repartidor sin tocar la base de datos.")
                        df_entregados = df_rep[df_rep['estatus'] == 'entregado']
                        if not df_entregados.empty:
                            df_por_repartidor = df_entregados.groupby('ruta').agg(
                                Pedidos_entregados=('id', 'count'),
                                Garrafones_20L=('cantidad_20L', 'sum'),
                                Garrafones_10L=('cantidad_10L', 'sum'),
                            ).reset_index().rename(columns={'ruta': 'Repartidor / Ruta'})
                            df_por_repartidor['Total_garrafones'] = df_por_repartidor['Garrafones_20L'] + df_por_repartidor['Garrafones_10L']
                            df_por_repartidor = df_por_repartidor.sort_values('Total_garrafones', ascending=False)
                            st.dataframe(df_por_repartidor, use_container_width=True)
                            st.bar_chart(df_por_repartidor.set_index('Repartidor / Ruta')['Total_garrafones'])
                            excel_repartidores = exportar_excel(df_por_repartidor)
                            st.download_button(label="📥 Exportar Ventas por Repartidor", data=excel_repartidores, file_name=f"repartidores_viteg_{datetime.now().strftime('%Y-%m-%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key="btn_export_repartidores")
                        else:
                            st.info("Todavía no hay pedidos entregados.")
                        st.divider()

                        df_rep['total_garrafones'] = df_rep['cantidad_20L'] + df_rep['cantidad_10L']
                        df_top = df_rep.nlargest(10, 'total_garrafones')[['nombre_cliente', 'ruta', 'cantidad_20L', 'cantidad_10L', 'total_garrafones', 'estatus']]
                        st.dataframe(df_top, use_container_width=True)
                        excel_reporte = exportar_excel(df_por_ruta)
                        st.download_button(label="📥 Exportar Reporte a Excel", data=excel_reporte, file_name=f"reporte_viteg_{datetime.now().strftime('%Y-%m-%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                    else:
                        st.info("No hay datos suficientes.")
                except Exception as e:
                    st.error(f"Error en reportes: {e}")

# ==========================================
# VISTA REPARTIDOR
# ==========================================
else:

    # --- RUTA REPARTIDOR ---
    if seccion_rep == "🚚 Mi Ruta de Entrega":
        st.subheader("🚚 Mi Ruta de Entrega")
        with get_db() as db:
            if db:
                try:
                    df_chofer = pd.read_sql("SELECT id, nombre_cliente, telefono, ruta, cantidad_20L, cantidad_10L, referencia, estatus, latitud, longitud FROM pedidos WHERE estatus != 'entregado'", db)
                    if not df_chofer.empty:
                        rutas_chofer = sorted(list(df_chofer['ruta'].unique()))
                        ruta_sel = st.selectbox("Selecciona tu Ruta / Zona:", rutas_chofer, key="chofer_ruta_sel_rep")
                        if st.session_state.ruta_sel_previa != ruta_sel:
                            st.session_state.ruta_optimizada = False
                            st.session_state.df_ruta_ordenada = None
                            st.session_state.orden_manual = None
                            st.session_state.modo_reordenar = False
                            st.session_state.ruta_sel_previa = ruta_sel
                        df_ruta_base = df_chofer[df_chofer['ruta'] == ruta_sel].copy()
                        total_ruta = len(df_ruta_base)
                        with get_db() as db2:
                            if db2:
                                df_todos = pd.read_sql("SELECT estatus FROM pedidos WHERE ruta = %s", db2, params=(ruta_sel,))
                                entregados_hoy = len(df_todos[df_todos['estatus'] == 'entregado'])
                                total_ruta_completa = len(df_todos)
                        c1, c2, c3 = st.columns(3)
                        c1.metric("📦 Pendientes", total_ruta)
                        c2.metric("✅ Entregados", entregados_hoy)
                        progreso = int((entregados_hoy / total_ruta_completa) * 100) if total_ruta_completa > 0 else 0
                        c3.metric("📊 Progreso", f"{progreso}%")
                        st.progress(progreso / 100)
                        st.divider()
                        coords_validas = df_ruta_base[(df_ruta_base['latitud'] != 0) & (df_ruta_base['longitud'] != 0)].copy()
                        sin_coords = df_ruta_base[(df_ruta_base['latitud'] == 0) | (df_ruta_base['longitud'] == 0)].copy()
                        col_opt1, col_opt2, col_opt3 = st.columns(3)
                        with col_opt1:
                            btn_optimizar = st.button("🧭 OPTIMIZAR CON IA", use_container_width=True, type="primary", key="opt_rep")
                        with col_opt2:
                            btn_reordenar = st.button("✋ AJUSTAR MANUALMENTE", use_container_width=True, key="rea_rep")
                        with col_opt3:
                            btn_original = st.button("↩️ Orden original", use_container_width=True, key="ori_rep")
                        if btn_optimizar:
                            if len(coords_validas) >= 2:
                                df_optimizado = pd.concat([optimizar_ruta(coords_validas), sin_coords]).reset_index(drop=True)
                                st.session_state.df_ruta_ordenada = df_optimizado
                                st.session_state.orden_manual = None
                                st.session_state.ruta_optimizada = True
                                st.session_state.modo_reordenar = False
                            else:
                                st.warning("⚠️ Se necesitan al menos 2 clientes con GPS.")
                        if btn_reordenar:
                            st.session_state.modo_reordenar = True
                        if btn_original:
                            st.session_state.ruta_optimizada = False
                            st.session_state.df_ruta_ordenada = None
                            st.session_state.orden_manual = None
                            st.session_state.modo_reordenar = False
                        if st.session_state.ruta_optimizada and st.session_state.df_ruta_ordenada is not None:
                            df_ruta_actual = st.session_state.df_ruta_ordenada.copy()
                            st.success("✅ Ruta optimizada por IA.")
                        elif st.session_state.orden_manual is not None:
                            df_ruta_actual = st.session_state.orden_manual.copy()
                            st.success("✅ Orden ajustado manualmente.")
                        else:
                            df_ruta_actual = df_ruta_base.copy()
                        if st.session_state.modo_reordenar:
                            st.markdown("### ✋ Ajusta el orden manualmente")
                            if "lista_ids_manual" not in st.session_state or st.session_state.lista_ids_ruta != ruta_sel:
                                st.session_state.lista_ids_manual = list(df_ruta_actual['id'])
                                st.session_state.lista_ids_ruta = ruta_sel
                            ids_orden = st.session_state.lista_ids_manual
                            df_orden = df_ruta_actual.set_index('id').loc[ids_orden].reset_index()
                            for i, (_, row) in enumerate(df_orden.iterrows()):
                                col_n, col_u, col_d = st.columns([6, 1, 1])
                                col_n.write(f"**#{i+1}** — {row['nombre_cliente']}")
                                if i > 0:
                                    if col_u.button("⬆️", key=f"up_r_{row['id']}_{i}"):
                                        ids_orden[i], ids_orden[i-1] = ids_orden[i-1], ids_orden[i]
                                        st.session_state.lista_ids_manual = ids_orden
                                        st.rerun()
                                if i < len(df_orden) - 1:
                                    if col_d.button("⬇️", key=f"dn_r_{row['id']}_{i}"):
                                        ids_orden[i], ids_orden[i+1] = ids_orden[i+1], ids_orden[i]
                                        st.session_state.lista_ids_manual = ids_orden
                                        st.rerun()
                            if st.button("✅ Confirmar orden", type="primary", use_container_width=True, key="conf_rep"):
                                df_manual = df_ruta_actual.set_index('id').loc[st.session_state.lista_ids_manual].reset_index()
                                st.session_state.orden_manual = df_manual
                                st.session_state.ruta_optimizada = False
                                st.session_state.modo_reordenar = False
                                st.rerun()
                            st.divider()
                        df_maps = df_ruta_actual[(df_ruta_actual['latitud'] != 0) & (df_ruta_actual['longitud'] != 0)]
                        if len(df_maps) > 1:
                            origen = f"{df_maps.iloc[0]['latitud']},{df_maps.iloc[0]['longitud']}"
                            destino = f"{df_maps.iloc[-1]['latitud']},{df_maps.iloc[-1]['longitud']}"
                            url_ruta_completa = f"https://www.google.com/maps/dir/{origen}/{destino}"
                            label = "🗺️ VER RUTA OPTIMIZADA" if st.session_state.ruta_optimizada else "🗺️ VER RUTA COMPLETA"
                            st.markdown(f'<a href="{url_ruta_completa}" target="_blank"><button style="background-color:#34A853;color:white;border:none;padding:12px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;font-size:15px;margin-bottom:10px;">{label}</button></a>', unsafe_allow_html=True)
                        st.divider()
                        titulo_lista = "🧭 Orden optimizado" if st.session_state.ruta_optimizada else "📋 Pedidos activos"
                        st.markdown(f"### {titulo_lista}: {ruta_sel} ({total_ruta} restantes)")
                        for idx, (_, row) in enumerate(df_ruta_actual.iterrows(), start=1):
                            num_tel = str(row['telefono']).strip() if row['telefono'] else "S/N"
                            prefix_icon = "⏳" if row['estatus'] == 'pendiente' else "❌"
                            num_parada = f"#{idx} — " if st.session_state.ruta_optimizada else ""
                            with st.expander(f"{prefix_icon} {num_parada}{row['nombre_cliente']} | {num_tel}"):
                                st.write(f"🛒 {row['cantidad_20L']} Garrafones 20L | {row['cantidad_10L']} Garrafones 10L")
                                texto_ref, foto_url = extraer_foto_y_texto(row['referencia'])
                                st.write(f"🏠 Referencias: {texto_ref if texto_ref else 'Sin notas'}")
                                if foto_url:
                                    st.markdown(f'<a href="{foto_url}" target="_blank">📷 Ver foto de referencia</a>', unsafe_allow_html=True)
                                    try:
                                        st.image(foto_url, width=250)
                                    except Exception:
                                        pass
                                if row['latitud'] != 0 and row['longitud'] != 0:
                                    url_gmaps = f"https://www.google.com/maps/search/?api=1&query={row['latitud']},{row['longitud']}"
                                    st.markdown(f'<a href="{url_gmaps}" target="_blank"><button style="background-color:#1a73e8;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">🗺️ NAVEGAR</button></a>', unsafe_allow_html=True)
                                if num_tel != "S/N" and len(num_tel) >= 10:
                                    c1, c2, c3 = st.columns(3)
                                    with c1:
                                        st.markdown(f'<a href="tel:{num_tel}"><button style="background-color:#007BFF;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">📞 LLAMAR</button></a>', unsafe_allow_html=True)
                                    with c2:
                                        msg_afuera = "Hola, le avisamos de Agua VITEG 💧. El camión ya está afuera. ¡Gracias!"
                                        st.markdown(f'<a href="{enviar_whatsapp_link(num_tel, msg_afuera)}" target="_blank"><button style="background-color:#25D366;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">📲 YA ESTOY AFUERA</button></a>', unsafe_allow_html=True)
                                    with c3:
                                        msg_ent = f"Hola {row['nombre_cliente']}, su pedido fue entregado. ¡Gracias!"
                                        st.markdown(f'<a href="{enviar_whatsapp_link(num_tel, msg_ent)}" target="_blank"><button style="background-color:#128C7E;color:white;border:none;padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">✅ CONFIRMAR</button></a>', unsafe_allow_html=True)
                                st.markdown("---")
                                col_e1, col_e2 = st.columns(2)
                                with col_e1:
                                    if st.button("✅ Marcar Entregado", key=f"ent_r_{row['id']}"):
                                        cursor = db.cursor()
                                        cursor.execute("UPDATE pedidos SET estatus = 'entregado' WHERE id = %s", (row['id'],))
                                        db.commit()
                                        cursor.close()
                                        st.session_state.ruta_optimizada = False
                                        st.session_state.df_ruta_ordenada = None
                                        st.rerun()
                                with col_e2:
                                    if row['estatus'] != 'no encontrado':
                                        if st.button("❌ No Encontrado", key=f"noe_r_{row['id']}"):
                                            cursor = db.cursor()
                                            cursor.execute("UPDATE pedidos SET estatus = 'no encontrado' WHERE id = %s", (row['id'],))
                                            db.commit()
                                            cursor.close()
                                            st.rerun()
                    else:
                        st.success("🚚 ¡No hay pedidos pendientes!")
                except Exception as e:
                    st.error(f"Error: {e}")

    # --- REGISTRO REPARTIDOR ---
    if seccion_rep == "📝 Registrar Cliente":
        st.subheader("📝 Registrar Cliente")
        opciones_rutas_r = ["-- Escribir nueva ruta --"]
        with get_db() as db_rutas:
            if db_rutas:
                cursor_r = db_rutas.cursor()
                cursor_r.execute("SELECT DISTINCT ruta FROM pedidos WHERE ruta IS NOT NULL AND ruta != ''")
                for row_r in cursor_r.fetchall():
                    if row_r[0] not in opciones_rutas_r:
                        opciones_rutas_r.append(row_r[0])
                cursor_r.close()
        st.markdown("### 🔍 Buscador de Clientes")
        busqueda_r = st.text_input("Buscar por nombre o teléfono:", key="busqueda_rep")
        if busqueda_r:
            with get_db() as db_bus:
                if db_bus:
                    df_bus = pd.read_sql("SELECT id, nombre_cliente, telefono, ruta, referencia, estatus FROM pedidos WHERE nombre_cliente LIKE %s OR telefono LIKE %s", db_bus, params=(f"%{busqueda_r}%", f"%{busqueda_r}%"))
                    if not df_bus.empty:
                        st.dataframe(df_bus, use_container_width=True)
                    else:
                        st.info("No se encontraron resultados.")
        st.divider()
        location = streamlit_geolocation()
        lat_val_r, lon_val_r = 0.0, 0.0
        if location and isinstance(location, dict) and location.get("latitude") is not None:
            lat_val_r = float(location["latitude"])
            lon_val_r = float(location["longitude"])
        with st.form("alta_rep", clear_on_submit=True):
            col_form1, col_form2 = st.columns(2)
            with col_form1:
                nom_r = st.text_input("Nombre completo:*")
                tel_r = st.text_input("Teléfono:")
                sel_ruta_r = st.selectbox("Ruta:", opciones_rutas_r)
                rut_r = st.text_input("Nueva ruta:") if sel_ruta_r == "-- Escribir nueva ruta --" else sel_ruta_r
                cant_20_r = st.number_input("Garrafones 20L:", min_value=0, value=0)
                cant_10_r = st.number_input("Garrafones 10L:", min_value=0, value=0)
            with col_form2:
                lat_f_r = st.number_input("Latitud:", value=lat_val_r, format="%.6f")
                lon_f_r = st.number_input("Longitud:", value=lon_val_r, format="%.6f")
                ref_r = st.text_input("Referencias:", help="📷 Tip: puedes pegar aquí un link a una foto de la fachada (súbela a Google Fotos/Drive y comparte el link público).")
            if st.form_submit_button("💾 Guardar", use_container_width=True):
                if nom_r and rut_r and rut_r.strip():
                    with get_db() as db_alta:
                        if db_alta:
                            try:
                                cursor_a = db_alta.cursor()
                                cursor_a.execute("INSERT INTO pedidos (nombre_cliente, telefono, ruta, cantidad_20L, cantidad_10L, referencia, estatus, latitud, longitud, direccion) VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', %s, %s, '')", (nom_r, tel_r, rut_r, cant_20_r, cant_10_r, ref_r, lat_f_r, lon_f_r))
                                db_alta.commit()
                                cursor_a.close()
                                st.success(f"🎉 '{nom_r}' registrado en ruta: {rut_r}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                else:
                    st.error("Completa Nombre y Ruta.")

    # --- PREVENTA REPARTIDOR ---
    if seccion_rep == "📲 Notificaciones de Preventa":
        st.subheader("📲 Notificaciones de Preventa")
        plantilla_prev_r = st.text_area("Plantilla recordatorio:", value="Hola {nombre}, le escribimos de Agua VITEG 💧. Mañana el camión pasará por su zona ({ruta}). ¡Nos vemos!", height=80)
        st.divider()
        with get_db() as db:
            if db:
                try:
                    df_notif_r = pd.read_sql("SELECT nombre_cliente, telefono, ruta FROM pedidos", db)
                    if not df_notif_r.empty:
                        rutas_notif_r = sorted([r.strip() for r in df_notif_r['ruta'].unique() if r])
                        ruta_notif_r = st.selectbox("Seleccionar Ruta:", rutas_notif_r, key="ruta_prev_rep")
                        df_clientes_r = df_notif_r[df_notif_r['ruta'] == ruta_notif_r]
                        st.markdown(f"**{len(df_clientes_r)} clientes**")
                        st.divider()
                        for _, row_c in df_clientes_r.iterrows():
                            nombre = row_c['nombre_cliente']
                            telefono = str(row_c['telefono']).strip() if row_c['telefono'] else ""
                            if telefono and len(telefono) >= 10:
                                msg = plantilla_prev_r.replace("{nombre}", nombre).replace("{ruta}", ruta_notif_r)
                                col_c1, col_c2 = st.columns([3, 1])
                                col_c1.write(f"👤 {nombre} ({telefono})")
                                col_c2.markdown(f'<a href="{enviar_whatsapp_link(telefono, msg)}" target="_blank">📲 Enviar</a>', unsafe_allow_html=True)
                            else:
                                st.warning(f"⚠️ {nombre} — sin teléfono.")
                except Exception as e:
                    st.error(f"Error: {e}")

