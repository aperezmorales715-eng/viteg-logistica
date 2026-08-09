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
import re
import time
from typing import Optional, Tuple, Dict, List
import hashlib
import base64
import os

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Sistema Interno - Agua VITEG", 
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CONSTANTES Y CONFIGURACIÓN
# ==========================================
CONFIG = {
    'MAP_DEFAULT_CENTER': [19.3150, -98.2400],
    'DEFAULT_ZOOM': 13,
    'REFRESH_INTERVAL': 20000,
    'MAX_ROUTE_POINTS': 100,
    'SESSION_TIMEOUT': 3600,
    'CACHE_TTL': 60,
}

# ==========================================
# CONFIGURACIÓN DE BASE DE DATOS MEJORADA
# ==========================================
def get_db_config():
    """Obtiene la configuración de la base de datos con valores por defecto."""
    try:
        # Intentar obtener de secrets
        config = {
            'host': st.secrets.get("DB_HOST", "localhost"),
            'user': st.secrets.get("DB_USER", "root"),
            'password': st.secrets.get("DB_PASSWORD", ""),
            'database': st.secrets.get("DB_NAME", "viteg"),
            'port': int(st.secrets.get("DB_PORT", 3306)),
            'connection_timeout': 30,
            'autocommit': True,
            'charset': 'utf8mb4',
            'use_unicode': True,
            'get_warnings': True,
            'pool_name': 'mypool',
            'pool_size': 3,
        }
        return config
    except Exception:
        # Si no hay secrets, usar valores por defecto o variables de entorno
        return {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'user': os.environ.get('DB_USER', 'root'),
            'password': os.environ.get('DB_PASSWORD', ''),
            'database': os.environ.get('DB_NAME', 'viteg'),
            'port': int(os.environ.get('DB_PORT', 3306)),
            'connection_timeout': 30,
            'autocommit': True,
            'charset': 'utf8mb4',
            'use_unicode': True,
            'get_warnings': True,
            'pool_name': 'mypool',
            'pool_size': 3,
        }

# ==========================================
# CONEXIÓN A BD CON MANEJO DE ERRORES MEJORADO
# ==========================================
@contextmanager
def get_db():
    """Context manager para conexiones a la base de datos con manejo robusto."""
    db = None
    try:
        config = get_db_config()
        
        # Intentar conectar con reintentos
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                db = mysql.connector.connect(**config)
                if db and db.is_connected():
                    break
            except mysql.connector.Error as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay)
                continue
        
        if db and db.is_connected():
            yield db
        else:
            st.error("❌ No se pudo establecer conexión con la base de datos")
            yield None
            
    except mysql.connector.Error as e:
        error_code = e.errno
        error_msg = str(e)
        
        # Mensajes de error más amigables
        if error_code == 2003:
            st.error("❌ No se puede conectar al servidor MySQL. Verifica que el servidor esté en ejecución y la configuración de red.")
        elif error_code == 1045:
            st.error("❌ Acceso denegado. Verifica el usuario y contraseña.")
        elif error_code == 1049:
            st.error("❌ La base de datos no existe. Verifica el nombre de la base de datos.")
        elif error_code == 2013:
            st.error("❌ Error de conexión con el servidor MySQL. Verifica que el servidor esté en ejecución.")
        else:
            st.error(f"❌ Error de conexión: {error_msg}")
        
        yield None
    except Exception as e:
        st.error(f"❌ Error inesperado: {e}")
        yield None
    finally:
        if db and db.is_connected():
            try:
                db.close()
            except:
                pass

# ==========================================
# VERIFICACIÓN DE CONEXIÓN
# ==========================================
def verificar_conexion_bd():
    """Verifica si la conexión a la base de datos es exitosa."""
    with get_db() as db:
        if db:
            try:
                cursor = db.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
            except:
                return False
    return False

# ==========================================
# FUNCIÓN PARA CREAR TABLAS SI NO EXISTEN
# ==========================================
def inicializar_bd():
    """Crea las tablas necesarias si no existen."""
    with get_db() as db:
        if db:
            try:
                cursor = db.cursor()
                
                # Crear tabla pedidos
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pedidos (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        nombre_cliente VARCHAR(255) NOT NULL,
                        telefono VARCHAR(20),
                        ruta VARCHAR(100),
                        cantidad_20L INT DEFAULT 0,
                        cantidad_10L INT DEFAULT 0,
                        referencia TEXT,
                        estatus ENUM('pendiente', 'entregado', 'no encontrado') DEFAULT 'pendiente',
                        latitud DECIMAL(10, 8) DEFAULT 0,
                        longitud DECIMAL(11, 8) DEFAULT 0,
                        direccion TEXT,
                        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_ruta (ruta),
                        INDEX idx_estatus (estatus),
                        INDEX idx_nombre (nombre_cliente)
                    )
                """)
                
                # Crear tabla usuarios (para futura expansión)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        nombre VARCHAR(100),
                        email VARCHAR(100) UNIQUE,
                        password_hash VARCHAR(255),
                        rol ENUM('admin', 'repartidor') DEFAULT 'repartidor',
                        activo BOOLEAN DEFAULT TRUE,
                        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                db.commit()
                cursor.close()
                return True
            except Exception as e:
                st.error(f"❌ Error al inicializar la base de datos: {e}")
                return False
    return False

# ==========================================
# ESTILO VISUAL MEJORADO
# ==========================================
st.markdown("""
<style>
    :root {
        --viteg-azul: #1a73e8;
        --viteg-azul-claro: #EAF2FE;
        --viteg-azul-oscuro: #1557b0;
        --viteg-verde: #25D366;
        --viteg-rojo: #ea4335;
        --viteg-naranja: #fbbc04;
    }

    .main {
        padding: 0rem 1rem;
    }

    div.stButton > button {
        border-radius: 24px;
        font-weight: 600;
        border: 1px solid #DCEBFC;
        transition: all 0.3s ease;
        padding: 0.5rem 1rem;
    }
    
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(26, 115, 232, 0.3);
    }
    
    div.stButton > button[kind="primary"] {
        background-color: var(--viteg-azul);
        border-color: var(--viteg-azul);
        color: white;
    }
    
    div.stButton > button[kind="primary"]:hover {
        background-color: var(--viteg-azul-oscuro);
    }

    [data-testid="stMetric"] {
        background-color: var(--viteg-azul-claro);
        border-radius: 14px;
        padding: 16px 12px;
        border: 1px solid #DCEBFC;
        transition: all 0.3s ease;
    }
    
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    [data-testid="stMetricLabel"] {
        font-weight: 600;
        color: #333;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--viteg-azul);
    }

    [data-testid="stExpander"] {
        border-radius: 14px;
        border: 1px solid #E3ECF5;
        margin-bottom: 12px;
        overflow: hidden;
        transition: all 0.3s ease;
        background-color: white;
    }
    
    [data-testid="stExpander"]:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    [data-testid="stExpander"] summary {
        font-weight: 600;
        padding: 12px 8px;
        background-color: #f8fafc;
    }

    div[data-baseweb="select"] > div, 
    .stTextInput input, 
    .stNumberInput input, 
    .stTextArea textarea {
        border-radius: 10px !important;
        border: 1px solid #DCEBFC !important;
        transition: border-color 0.3s ease;
    }
    
    div[data-baseweb="select"] > div:focus-within,
    .stTextInput input:focus,
    .stNumberInput input:focus,
    .stTextArea textarea:focus {
        border-color: var(--viteg-azul) !important;
        box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.2) !important;
    }

    .stProgress > div > div > div {
        background: linear-gradient(90deg, var(--viteg-azul), var(--viteg-verde));
        border-radius: 10px;
    }

    hr {
        margin: 0.8rem 0;
        opacity: 0.15;
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--viteg-azul), transparent);
    }

    .stAlert {
        border-radius: 12px;
        border-left: 4px solid var(--viteg-azul);
    }
    
    .stAlert > div {
        padding: 0.8rem 1.2rem;
    }

    section[data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e5e7eb;
    }
    
    section[data-testid="stSidebar"] > div {
        padding-top: 2rem;
    }

    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 0.1rem;
    }
    
    .badge-success {
        background-color: #d4edda;
        color: #155724;
    }
    
    .badge-warning {
        background-color: #fff3cd;
        color: #856404;
    }
    
    .badge-danger {
        background-color: #f8d7da;
        color: #721c24;
    }
    
    .badge-info {
        background-color: #d1ecf1;
        color: #0c5460;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .fade-in {
        animation: fadeIn 0.5s ease-out;
    }

    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #E3ECF5;
    }
    
    .stDataFrame table {
        font-size: 0.9rem;
    }
    
    .stDataFrame thead {
        background-color: #f8fafc;
    }

    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--viteg-azul);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--viteg-azul-oscuro);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# FUNCIONES DE SEGURIDAD
# ==========================================
def hash_password(password: str) -> str:
    """Genera un hash seguro de la contraseña."""
    salt = st.secrets.get("PASSWORD_SALT", "viteg_salt_2024")
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()

def verificar_contraseña(password: str, hash_almacenado: str) -> bool:
    """Verifica si la contraseña coincide con el hash almacenado."""
    return hash_password(password) == hash_almacenado

def verificar_sesion():
    """Verifica si la sesión ha expirado."""
    if 'session_start' in st.session_state:
        tiempo_transcurrido = time.time() - st.session_state.session_start
        if tiempo_transcurrido > CONFIG['SESSION_TIMEOUT']:
            st.session_state.rol = None
            st.session_state.nav_actual = None
            st.warning("⏰ Sesión expirada. Por favor, inicia sesión nuevamente.")
            st.rerun()
    else:
        st.session_state.session_start = time.time()

# ==========================================
# LOGIN MEJORADO
# ==========================================
CLAVE_ADMIN = st.secrets.get("CLAVE_ADMIN", "viteg2024")
CLAVE_REPARTIDOR = st.secrets.get("CLAVE_REPARTIDOR", "reparto123")
HASH_ADMIN = hash_password(CLAVE_ADMIN)
HASH_REPARTIDOR = hash_password(CLAVE_REPARTIDOR)

if "rol" not in st.session_state:
    st.session_state.rol = None
    st.session_state.intentos_fallidos = 0

# Verificar conexión a BD antes del login
if not verificar_conexion_bd():
    st.error("""
    ⚠️ **No se puede conectar a la base de datos**
    
    Por favor, verifica que:
    1. El servidor MySQL esté en ejecución
    2. La configuración en `.streamlit/secrets.toml` sea correcta
    3. El usuario y contraseña sean válidos
    4. La base de datos exista
    
    **Configuración actual:**
    """)
    
    try:
        config = get_db_config()
        st.code(f"""
        Host: {config['host']}
        Puerto: {config['port']}
        Usuario: {config['user']}
        Base de datos: {config['database']}
        """)
    except:
        pass
    
    st.info("💡 Puedes configurar la base de datos creando el archivo `.streamlit/secrets.toml`")
    
    # Opción para inicializar BD
    if st.button("🔄 Intentar inicializar base de datos", use_container_width=True):
        if inicializar_bd():
            st.success("✅ Base de datos inicializada correctamente")
            st.rerun()
        else:
            st.error("❌ No se pudo inicializar la base de datos")
    
    st.stop()

if st.session_state.rol is None:
    if st.session_state.intentos_fallidos >= 5:
        st.error("🔒 Demasiados intentos fallidos. Espera 5 minutos.")
        time.sleep(300)
        st.session_state.intentos_fallidos = 0
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        try:
            st.image("logo.jpeg", width=250)
        except:
            st.markdown("### 💧 Agua VITEG")
        st.title("Sistema de Gestión Logística")
        st.markdown("---")
        
        clave = st.text_input("🔑 Contraseña:", type="password", placeholder="Ingresa tu contraseña")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("👔 Administrador", use_container_width=True, type="primary"):
                if clave and verificar_contraseña(clave, HASH_ADMIN):
                    st.session_state.rol = "admin"
                    st.session_state.session_start = time.time()
                    st.session_state.intentos_fallidos = 0
                    st.rerun()
                else:
                    st.session_state.intentos_fallidos += 1
                    st.error(f"❌ Contraseña incorrecta. Intentos: {st.session_state.intentos_fallidos}/5")
        
        with col_btn2:
            if st.button("🚚 Repartidor", use_container_width=True):
                if clave and verificar_contraseña(clave, HASH_REPARTIDOR):
                    st.session_state.rol = "repartidor"
                    st.session_state.session_start = time.time()
                    st.session_state.intentos_fallidos = 0
                    st.rerun()
                else:
                    st.session_state.intentos_fallidos += 1
                    st.error(f"❌ Contraseña incorrecta. Intentos: {st.session_state.intentos_fallidos}/5")
        
        st.markdown("---")
        st.caption("💡 Contacta al administrador si necesitas acceso.")
    st.stop()

verificar_sesion()

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def reiniciar_ruta_completa(nombre_ruta: str) -> bool:
    with get_db() as db:
        if db:
            try:
                cursor = db.cursor()
                cursor.execute(
                    "UPDATE pedidos SET estatus = 'pendiente' WHERE ruta = %s",
                    (nombre_ruta,)
                )
                db.commit()
                cursor.close()
                return True
            except Exception as e:
                st.error(f"Error al reiniciar ruta: {e}")
    return False

def enviar_whatsapp_link(telefono: str, mensaje: str) -> str:
    try:
        tel = str(telefono).strip()
        tel = re.sub(r'[^0-9]', '', tel)
        if not tel.startswith("52"):
            tel = f"52{tel}"
        return f"https://wa.me/{tel}?text={urllib.parse.quote(mensaje)}"
    except Exception:
        return "#"

def extraer_foto_y_texto(referencia: str) -> Tuple[str, Optional[str]]:
    if not referencia:
        return "", None
    try:
        url_pattern = r'(https?://\S+)'
        match = re.search(url_pattern, str(referencia))
        if match:
            url = match.group(1)
            texto_limpio = str(referencia).replace(url, "").strip(" -,.:;")
            return texto_limpio, url
        return referencia, None
    except Exception:
        return referencia, None

def exportar_excel(df: pd.DataFrame) -> bytes:
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Pedidos')
        return output.getvalue()
    except Exception as e:
        st.error(f"Error al exportar a Excel: {e}")
        return b""

def optimizar_ruta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    
    df = df.reset_index(drop=True)
    coords = df[['latitud', 'longitud']].values
    
    if len(coords) <= 1:
        return df
    
    try:
        coords = coords.astype(float)
        n = len(coords)
        
        diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
        dist_matrix = np.sqrt((diff ** 2).sum(axis=2))
        
        visitado = [False] * n
        orden = []
        
        centro = coords.mean(axis=0)
        distancias_al_centro = np.sqrt(((coords - centro) ** 2).sum(axis=1))
        actual = int(np.argmin(distancias_al_centro))
        
        for _ in range(n):
            visitado[actual] = True
            orden.append(actual)
            distancias = dist_matrix[actual].copy()
            distancias[visitado] = np.inf
            siguiente = int(np.argmin(distancias))
            actual = siguiente
        
        return df.iloc[orden].reset_index(drop=True)
    except Exception as e:
        st.warning(f"Error en optimización: {e}. Usando orden original.")
        return df

def validar_telefono(telefono: str) -> bool:
    if not telefono:
        return False
    tel = re.sub(r'[^0-9]', '', str(telefono))
    return len(tel) >= 10 and len(tel) <= 15

# ==========================================
# INICIALIZAR BASE DE DATOS (si es necesario)
# ==========================================
if verificar_conexion_bd():
    inicializar_bd()

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
            st.session_state.session_start = None
            st.rerun()
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

@st.dialog("⚠️ Confirmar reinicio de TODAS las rutas")
def dialogo_reiniciar_todo():
    st.error("⚠️ Esta acción marcará TODOS los pedidos como 'pendiente'.\nNo se puede deshacer.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, reiniciar todo", type="primary", use_container_width=True):
            with get_db() as db:
                if db:
                    try:
                        cursor = db.cursor()
                        cursor.execute("UPDATE pedidos SET estatus = 'pendiente'")
                        db.commit()
                        cursor.close()
                        st.success("✅ Todos los pedidos reiniciados")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

@st.dialog("⚠️ Confirmar reinicio de ruta")
def dialogo_reiniciar_ruta(nombre_ruta: str):
    st.error(f"⚠️ Esta acción marcará todos los pedidos de **'{nombre_ruta}'** como 'pendiente'.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, reiniciar", type="primary", use_container_width=True):
            if reiniciar_ruta_completa(nombre_ruta):
                st.success(f"✅ Ruta '{nombre_ruta}' reiniciada")
                time.sleep(1)
                st.rerun()
    with c2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.rerun()

@st.dialog("🗑️ Confirmar eliminación de cliente")
def dialogo_eliminar_cliente(id_cliente: int, nombre_cliente: str):
    st.error(f"⚠️ ¿Eliminar permanentemente a **{nombre_cliente}**?\nEsta acción no se puede deshacer.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Sí, eliminar", type="primary", use_container_width=True):
            with get_db() as db:
                if db:
                    try:
                        cursor = db.cursor()
                        cursor.execute("DELETE FROM pedidos WHERE id = %s", (id_cliente,))
                        db.commit()
                        cursor.close()
                        st.success("✅ Cliente eliminado")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
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
    "ultimo_refresh": time.time(),
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    try:
        st.image("logo.jpeg", use_column_width=True)
    except:
        st.markdown("### 💧 Agua VITEG")
    
    st.markdown("---")
    
    rol_icon = "👔" if st.session_state.rol == "admin" else "🚚"
    rol_name = "Administrador" if st.session_state.rol == "admin" else "Repartidor"
    st.markdown(f"**{rol_icon} {rol_name}**")
    st.markdown(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # Estado de conexión
    st.markdown("---")
    if verificar_conexion_bd():
        st.success("🟢 Base de datos conectada")
    else:
        st.error("🔴 Base de datos desconectada")
    
    st.markdown("---")
    
    with get_db() as db:
        if db:
            try:
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM pedidos WHERE estatus = 'pendiente'")
                pendientes_total = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM pedidos WHERE estatus = 'entregado'")
                entregados_total = cursor.fetchone()[0]
                cursor.close()
                
                col1, col2 = st.columns(2)
                col1.metric("⏳ Pendientes", pendientes_total)
                col2.metric("✅ Entregados", entregados_total)
            except:
                pass
    
    st.markdown("---")
    
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        dialogo_cerrar_sesion()

# ==========================================
# TÍTULO PRINCIPAL
# ==========================================
try:
    col_logo, col_titulo = st.columns([1, 5])
    with col_logo:
        st.image("logo.jpeg", width=100)
    with col_titulo:
        st.title("💧 Sistema de Gestión Logística - Agua VITEG")
        st.markdown("Panel de control interno para el monitoreo de rutas, despacho de repartidores y análisis de demanda.")
except:
    st.title("💧 Sistema de Gestión Logística - Agua VITEG")

# ==========================================
# NAVEGACIÓN
# ==========================================
SECCIONES_ADMIN = ["📍 Mapa", "🚚 Panel Chofer", "📝 Registro", "📲 Preventa", "📊 Administrador", "📈 Reportes"]
SECCIONES_REP = ["🚚 Mi Ruta", "📝 Registrar", "📲 Preventa"]

if st.session_state.get("nav_actual") is None:
    st.session_state.nav_actual = SECCIONES_ADMIN[0] if st.session_state.rol == "admin" else SECCIONES_REP[0]

opciones_nav = SECCIONES_ADMIN if st.session_state.rol == "admin" else SECCIONES_REP

if st.session_state.nav_actual not in opciones_nav:
    st.session_state.nav_actual = opciones_nav[0]

cols_nav = st.columns(min(len(opciones_nav), 4))
for i, op in enumerate(opciones_nav):
    with cols_nav[i % len(cols_nav)]:
        es_actual = st.session_state.nav_actual == op
        if st.button(
            op, 
            key=f"nav_{op}", 
            use_container_width=True, 
            type="primary" if es_actual else "secondary"
        ):
            st.session_state.nav_actual = op
            st.rerun()

st.divider()

if st.session_state.rol == "admin":
    seccion = st.session_state.nav_actual
else:
    _mapa_rep = {
        "🚚 Mi Ruta": "🚚 Mi Ruta de Entrega",
        "📝 Registrar": "📝 Registrar Cliente",
        "📲 Preventa": "📲 Notificaciones de Preventa",
    }
    seccion_rep = _mapa_rep[st.session_state.nav_actual]

# ==========================================
# DETECCIÓN DE NUEVOS PEDIDOS (solo si hay BD)
# ==========================================
if verificar_conexion_bd():
    with get_db() as db:
        if db:
            try:
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(id), MAX(id) FROM pedidos")
                total_actual, id_max_actual = cursor.fetchone()
                cursor.close()
                
                if st.session_state.ultimo_conteo_pedidos == 0:
                    st.session_state.ultimo_conteo_pedidos = total_actual or 0
                    st.session_state.id_max_previo = id_max_actual or 0
                
                if (total_actual or 0) > st.session_state.ultimo_conteo_pedidos or (id_max_actual or 0) > st.session_state.id_max_previo:
                    with get_db() as db2:
                        if db2:
                            df_nuevo = pd.read_sql(
                                "SELECT nombre_cliente, ruta, referencia FROM pedidos ORDER BY id DESC LIMIT 1",
                                db2
                            )
                            if not df_nuevo.empty:
                                p = df_nuevo.iloc[0]
                                st.session_state.detalles_nuevo_pedido = {
                                    "cliente": p['nombre_cliente'],
                                    "ruta": p['ruta'] or "Sin Ruta",
                                    "referencia": p['referencia'] or "Sin referencias"
                                }
                                st.session_state.alerta_pendiente = True
                    
                    st.session_state.ultimo_conteo_pedidos = total_actual or 0
                    st.session_state.id_max_previo = id_max_actual or 0
            except:
                pass

# Mostrar alerta de nuevo pedido
if st.session_state.alerta_pendiente:
    d = st.session_state.detalles_nuevo_pedido
    with st.container():
        st.error(f"""
        🚨 **¡NUEVO PEDIDO!**
        - **Cliente:** {d.get('cliente')}
        - **Ruta:** {d.get('ruta')}
        - **Referencia:** {d.get('referencia')}
        """)
        if st.button("✅ Confirmar lectura", key="btn_limpiar_alerta", use_container_width=True):
            st.session_state.alerta_pendiente = False
            st.rerun()
    st.divider()

# ==========================================
# RENDERIZADO ADMIN (solo si hay BD)
# ==========================================
if st.session_state.rol == "admin":

    # --- MAPA ---
    if seccion == "📍 Mapa":
        st.subheader("🗺️ Monitoreo Geográfico de Pedidos")
        streamlit_autorefresh.st_autorefresh(
            interval=CONFIG['REFRESH_INTERVAL'], 
            key="mapa_refresh"
        )
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se puede cargar el mapa.")
        else:
            with get_db() as db:
                if db:
                    try:
                        df_mapa_todo = pd.read_sql(
                            "SELECT * FROM pedidos WHERE latitud != 0 AND longitud != 0",
                            db
                        )
                        
                        if not df_mapa_todo.empty:
                            df_mapa_todo['latitud'] = pd.to_numeric(df_mapa_todo['latitud'], errors='coerce')
                            df_mapa_todo['longitud'] = pd.to_numeric(df_mapa_todo['longitud'], errors='coerce')
                            df_mapa_todo = df_mapa_todo.dropna(subset=['latitud', 'longitud'])
                        
                        if not df_mapa_todo.empty:
                            col_f1, col_f2 = st.columns(2)
                            with col_f1:
                                rutas_disponibles = ["Todas"] + sorted(df_mapa_todo['ruta'].dropna().unique().tolist())
                                filtro_ruta = st.selectbox(
                                    "🗂️ Filtrar por ruta:", 
                                    rutas_disponibles, 
                                    key="map_ruta_filter"
                                )
                            with col_f2:
                                filtro_estatus = st.selectbox(
                                    "📌 Filtrar por estatus:", 
                                    ["Todos", "Pendientes", "Entregados", "No Encontrados"],
                                    key="map_estatus_filter"
                                )
                            
                            df_mapa = df_mapa_todo.copy()
                            if filtro_ruta != "Todas":
                                df_mapa = df_mapa[df_mapa['ruta'] == filtro_ruta]
                            
                            mapa_filtros = {
                                "Pendientes": "pendiente",
                                "Entregados": "entregado",
                                "No Encontrados": "no encontrado"
                            }
                            
                            if filtro_estatus in mapa_filtros:
                                df_filtrado = df_mapa[df_mapa['estatus'] == mapa_filtros[filtro_estatus]]
                            else:
                                df_filtrado = df_mapa
                            
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("📍 Total visibles", len(df_mapa))
                            c2.metric("⏳ Pendientes", len(df_mapa[df_mapa['estatus'] == 'pendiente']))
                            c3.metric("✅ Entregados", len(df_mapa[df_mapa['estatus'] == 'entregado']))
                            c4.metric("❌ No encontrados", len(df_mapa[df_mapa['estatus'] == 'no encontrado']))
                            
                            if not df_filtrado.empty and df_filtrado['latitud'].notna().any():
                                centro_lat = df_filtrado['latitud'].mean()
                                centro_lon = df_filtrado['longitud'].mean()
                                if pd.isna(centro_lat) or pd.isna(centro_lon) or (centro_lat == 0 and centro_lon == 0):
                                    centro_lat, centro_lon = CONFIG['MAP_DEFAULT_CENTER']
                            else:
                                centro_lat, centro_lon = CONFIG['MAP_DEFAULT_CENTER']
                            
                            zoom = 14 if filtro_ruta != "Todas" else CONFIG['DEFAULT_ZOOM']
                            m = folium.Map(
                                location=[centro_lat, centro_lon],
                                zoom_start=zoom,
                                tiles='OpenStreetMap'
                            )
                            
                            colores = {
                                "pendiente": ("red", "info-sign"),
                                "no encontrado": ("orange", "remove-sign"),
                                "entregado": ("green", "ok-sign")
                            }
                            
                            for _, row in df_filtrado.iterrows():
                                color, icono = colores.get(row['estatus'], ("blue", "question-sign"))
                                url_gmaps = f"https://www.google.com/maps/search/?api=1&query={row['latitud']},{row['longitud']}"
                                popup_text = f"""
                                <b>Cliente:</b> {row['nombre_cliente']}<br>
                                <b>Zona:</b> {row['ruta']}<br>
                                <b>Estatus:</b> {row['estatus'].upper()}<br>
                                <b>Garrafones:</b> {row['cantidad_20L']}x20L, {row['cantidad_10L']}x10L<br>
                                <a href='{url_gmaps}' target='_blank'>📍 Ver en Google Maps</a>
                                """
                                folium.Marker(
                                    location=[row['latitud'], row['longitud']],
                                    popup=folium.Popup(popup_text, max_width=300),
                                    icon=folium.Icon(color=color, icon=icono)
                                ).add_to(m)
                            
                            st_folium(m, width=1200, height=500, returned_objects=[])
                        else:
                            st.info("ℹ️ No hay pedidos con coordenadas registradas.")
                            
                    except Exception as e:
                        st.error(f"❌ Error al cargar el mapa: {e}")

    # --- PANEL CHOFER ---
    if seccion == "🚚 Panel Chofer":
        st.subheader("🚚 Panel del Chofer")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se puede cargar el panel.")
        else:
            with get_db() as db:
                if db:
                    try:
                        df_chofer = pd.read_sql(
                            """
                            SELECT id, nombre_cliente, telefono, ruta, 
                                   cantidad_20L, cantidad_10L, referencia, 
                                   estatus, latitud, longitud 
                            FROM pedidos 
                            WHERE estatus != 'entregado'
                            """,
                            db
                        )
                        
                        if not df_chofer.empty:
                            rutas_chofer = sorted(list(df_chofer['ruta'].unique()))
                            ruta_sel = st.selectbox(
                                "Selecciona tu Ruta / Zona:",
                                rutas_chofer,
                                key="chofer_ruta_sel_admin"
                            )
                            
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
                                    df_todos = pd.read_sql(
                                        "SELECT estatus FROM pedidos WHERE ruta = %s",
                                        db2,
                                        params=(ruta_sel,)
                                    )
                                    entregados_hoy = len(df_todos[df_todos['estatus'] == 'entregado'])
                                    total_ruta_completa = len(df_todos)
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("📦 Pendientes", total_ruta)
                            c2.metric("✅ Entregados", entregados_hoy)
                            progreso = int((entregados_hoy / total_ruta_completa) * 100) if total_ruta_completa > 0 else 0
                            c3.metric("📊 Progreso", f"{progreso}%")
                            st.progress(progreso / 100)
                            st.divider()
                            
                            coords_validas = df_ruta_base[
                                (df_ruta_base['latitud'] != 0) & (df_ruta_base['longitud'] != 0)
                            ].copy()
                            sin_coords = df_ruta_base[
                                (df_ruta_base['latitud'] == 0) | (df_ruta_base['longitud'] == 0)
                            ].copy()
                            
                            col_opt1, col_opt2, col_opt3 = st.columns(3)
                            with col_opt1:
                                if st.button("🧭 OPTIMIZAR CON IA", use_container_width=True, type="primary", key="opt_admin"):
                                    if len(coords_validas) >= 2:
                                        df_optimizado = pd.concat([
                                            optimizar_ruta(coords_validas),
                                            sin_coords
                                        ]).reset_index(drop=True)
                                        st.session_state.df_ruta_ordenada = df_optimizado
                                        st.session_state.orden_manual = None
                                        st.session_state.ruta_optimizada = True
                                        st.session_state.modo_reordenar = False
                                        st.success("✅ Ruta optimizada por IA")
                                    else:
                                        st.warning("⚠️ Se necesitan al menos 2 clientes con GPS para optimizar.")
                            
                            with col_opt2:
                                if st.button("✋ AJUSTAR MANUALMENTE", use_container_width=True, key="rea_admin"):
                                    st.session_state.modo_reordenar = True
                            
                            with col_opt3:
                                if st.button("↩️ Orden original", use_container_width=True, key="ori_admin"):
                                    st.session_state.ruta_optimizada = False
                                    st.session_state.df_ruta_ordenada = None
                                    st.session_state.orden_manual = None
                                    st.session_state.modo_reordenar = False
                            
                            if st.session_state.ruta_optimizada and st.session_state.df_ruta_ordenada is not None:
                                df_ruta_actual = st.session_state.df_ruta_ordenada.copy()
                            elif st.session_state.orden_manual is not None:
                                df_ruta_actual = st.session_state.orden_manual.copy()
                            else:
                                df_ruta_actual = df_ruta_base.copy()
                            
                            if st.session_state.modo_reordenar:
                                st.markdown("### ✋ Ajusta el orden manualmente")
                                
                                if ("lista_ids_manual" not in st.session_state or 
                                    st.session_state.lista_ids_ruta != ruta_sel):
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
                                    df_manual = df_ruta_actual.set_index('id').loc[
                                        st.session_state.lista_ids_manual
                                    ].reset_index()
                                    st.session_state.orden_manual = df_manual
                                    st.session_state.ruta_optimizada = False
                                    st.session_state.modo_reordenar = False
                                    st.rerun()
                                
                                st.divider()
                            
                            df_maps = df_ruta_actual[
                                (df_ruta_actual['latitud'] != 0) & (df_ruta_actual['longitud'] != 0)
                            ]
                            
                            if len(df_maps) > 1:
                                origen = f"{df_maps.iloc[0]['latitud']},{df_maps.iloc[0]['longitud']}"
                                destino = f"{df_maps.iloc[-1]['latitud']},{df_maps.iloc[-1]['longitud']}"
                                url_ruta_completa = f"https://www.google.com/maps/dir/{origen}/{destino}"
                                label = "🗺️ VER RUTA OPTIMIZADA" if st.session_state.ruta_optimizada else "🗺️ VER RUTA COMPLETA"
                                st.markdown(
                                    f'<a href="{url_ruta_completa}" target="_blank">'
                                    f'<button style="background-color:#34A853;color:white;border:none;'
                                    f'padding:12px;border-radius:5px;width:100%;cursor:pointer;'
                                    f'font-weight:bold;font-size:15px;margin-bottom:10px;">'
                                    f'{label}</button></a>',
                                    unsafe_allow_html=True
                                )
                            
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
                                        st.markdown(
                                            f'<a href="{foto_url}" target="_blank">📷 Ver foto de referencia</a>',
                                            unsafe_allow_html=True
                                        )
                                        try:
                                            st.image(foto_url, width=250)
                                        except:
                                            pass
                                    
                                    if row['latitud'] != 0 and row['longitud'] != 0:
                                        url_gmaps = f"https://www.google.com/maps/search/?api=1&query={row['latitud']},{row['longitud']}"
                                        st.markdown(
                                            f'<a href="{url_gmaps}" target="_blank">'
                                            f'<button style="background-color:#1a73e8;color:white;border:none;'
                                            f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                            f'🗺️ NAVEGAR</button></a>',
                                            unsafe_allow_html=True
                                        )
                                    
                                    if num_tel != "S/N" and validar_telefono(num_tel):
                                        c1, c2, c3 = st.columns(3)
                                        with c1:
                                            st.markdown(
                                                f'<a href="tel:{num_tel}">'
                                                f'<button style="background-color:#007BFF;color:white;border:none;'
                                                f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                                f'📞 LLAMAR</button></a>',
                                                unsafe_allow_html=True
                                            )
                                        with c2:
                                            msg_afuera = "Hola, le avisamos de Agua VITEG 💧. El camión ya está afuera. ¡Gracias!"
                                            st.markdown(
                                                f'<a href="{enviar_whatsapp_link(num_tel, msg_afuera)}" target="_blank">'
                                                f'<button style="background-color:#25D366;color:white;border:none;'
                                                f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                                f'📲 YA ESTOY AFUERA</button></a>',
                                                unsafe_allow_html=True
                                            )
                                        with c3:
                                            msg_ent = f"Hola {row['nombre_cliente']}, su pedido de Agua VITEG 💧 fue entregado. ¡Gracias!"
                                            st.markdown(
                                                f'<a href="{enviar_whatsapp_link(num_tel, msg_ent)}" target="_blank">'
                                                f'<button style="background-color:#128C7E;color:white;border:none;'
                                                f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                                f'✅ CONFIRMAR</button></a>',
                                                unsafe_allow_html=True
                                            )
                                    
                                    st.markdown("---")
                                    
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        if st.button("✅ Marcar Entregado", key=f"ent_a_{row['id']}"):
                                            cursor = db.cursor()
                                            cursor.execute(
                                                "UPDATE pedidos SET estatus = 'entregado' WHERE id = %s",
                                                (row['id'],)
                                            )
                                            db.commit()
                                            cursor.close()
                                            st.session_state.ruta_optimizada = False
                                            st.session_state.df_ruta_ordenada = None
                                            st.rerun()
                                    
                                    with col_e2:
                                        if row['estatus'] != 'no encontrado':
                                            if st.button("❌ No Encontrado", key=f"noe_a_{row['id']}"):
                                                cursor = db.cursor()
                                                cursor.execute(
                                                    "UPDATE pedidos SET estatus = 'no encontrado' WHERE id = %s",
                                                    (row['id'],)
                                                )
                                                db.commit()
                                                cursor.close()
                                                st.rerun()
                        else:
                            st.success("🚚 ¡No hay pedidos pendientes!")
                            
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    # --- REGISTRO ---
    if seccion == "📝 Registro":
        st.subheader("📝 Registro de Pedidos")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se puede registrar.")
        else:
            opciones_rutas = ["-- Escribir nueva ruta --"]
            with get_db() as db_rutas:
                if db_rutas:
                    try:
                        cursor_r = db_rutas.cursor()
                        cursor_r.execute("SELECT DISTINCT ruta FROM pedidos WHERE ruta IS NOT NULL AND ruta != ''")
                        for row_r in cursor_r.fetchall():
                            if row_r[0] not in opciones_rutas:
                                opciones_rutas.append(row_r[0])
                        cursor_r.close()
                    except:
                        pass
            
            st.markdown("### 🔍 Buscador de Clientes")
            busqueda = st.text_input("Buscar por nombre o teléfono:", key="busqueda_admin")
            
            if busqueda:
                with get_db() as db_bus:
                    if db_bus:
                        try:
                            df_bus = pd.read_sql(
                                """
                                SELECT id, nombre_cliente, telefono, ruta, referencia, estatus 
                                FROM pedidos 
                                WHERE nombre_cliente LIKE %s OR telefono LIKE %s
                                """,
                                db_bus,
                                params=(f"%{busqueda}%", f"%{busqueda}%")
                            )
                            if not df_bus.empty:
                                st.dataframe(df_bus, use_container_width=True)
                            else:
                                st.info("No se encontraron resultados.")
                        except:
                            st.warning("Error en la búsqueda")
            
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
                    tel = st.text_input("Teléfono Celular:", help="Formato: 5551234567")
                    sel_ruta = st.selectbox("Ruta:", opciones_rutas)
                    rut = st.text_input("Nueva ruta:") if sel_ruta == "-- Escribir nueva ruta --" else sel_ruta
                    cant_20 = st.number_input("Garrafones 20L:", min_value=0, value=0)
                    cant_10 = st.number_input("Garrafones 10L:", min_value=0, value=0)
                
                with col_form2:
                    lat_f = st.number_input("Latitud:", value=lat_val, format="%.6f")
                    lon_f = st.number_input("Longitud:", value=lon_val, format="%.6f")
                    ref = st.text_area(
                        "Referencias del domicilio:",
                        help="📷 Tip: puedes pegar aquí un link a una foto de la fachada",
                        height=100
                    )
                    st.caption("Ejemplo: Casa blanca, portón verde, link: https://fotos.com/...")
                
                if st.form_submit_button("💾 Guardar y Registrar", use_container_width=True, type="primary"):
                    if not nom or not nom.strip():
                        st.error("❌ El nombre del cliente es obligatorio")
                    elif not rut or not rut.strip():
                        st.error("❌ La ruta es obligatoria")
                    else:
                        with get_db() as db_alta:
                            if db_alta:
                                try:
                                    cursor_a = db_alta.cursor()
                                    cursor_a.execute(
                                        """
                                        INSERT INTO pedidos 
                                        (nombre_cliente, telefono, ruta, cantidad_20L, cantidad_10L, 
                                         referencia, estatus, latitud, longitud, direccion) 
                                        VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', %s, %s, '')
                                        """,
                                        (nom, tel, rut, cant_20, cant_10, ref, lat_f, lon_f)
                                    )
                                    db_alta.commit()
                                    cursor_a.close()
                                    
                                    st.success(f"🎉 Cliente '{nom}' registrado en ruta: {rut}")
                                    
                                    if tel and validar_telefono(tel):
                                        msg_conf = f"Hola {nom}, su pedido de Agua VITEG 💧 fue registrado. ¡Gracias!"
                                        st.markdown(
                                            f'<a href="{enviar_whatsapp_link(tel, msg_conf)}" target="_blank">'
                                            f'<button style="background-color:#25D366;color:white;border:none;'
                                            f'padding:10px;border-radius:5px;cursor:pointer;font-weight:bold;">'
                                            f'📲 Enviar confirmación por WhatsApp</button></a>',
                                            unsafe_allow_html=True
                                        )
                                    
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error al registrar: {e}")

    # --- PREVENTA ---
    if seccion == "📲 Preventa":
        st.subheader("📲 Notificaciones y Preventa")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se pueden cargar los clientes.")
        else:
            with st.expander("📝 Configuración de mensajes", expanded=True):
                plantilla_preventa = st.text_area(
                    "Plantilla de recordatorio (usa {nombre} y {ruta}):",
                    value="Hola {nombre}, le escribimos de Agua VITEG 💧. Le recordamos que mañana el camión pasará por su zona ({ruta}). ¡Nos vemos pronto!",
                    height=80,
                    key="plantilla_prev_admin"
                )
                
                plantilla_pedido_listo = st.text_area(
                    "Plantilla de pedido listo:",
                    value="Hola {nombre}, su pedido de Agua VITEG 💧 está listo y en camino. ¡Gracias!",
                    height=80,
                    key="plantilla_listo_admin"
                )
            
            st.divider()
            
            with get_db() as db:
                if db:
                    try:
                        df_notif = pd.read_sql(
                            "SELECT nombre_cliente, telefono, ruta FROM pedidos",
                            db
                        )
                        
                        if not df_notif.empty:
                            rutas_notif = sorted([r.strip() for r in df_notif['ruta'].unique() if r])
                            ruta_notif_sel = st.selectbox(
                                "Seleccionar Ruta:",
                                rutas_notif,
                                key="ruta_prev_admin"
                            )
                            
                            df_clientes_ruta = df_notif[df_notif['ruta'] == ruta_notif_sel]
                            st.markdown(f"**👥 {len(df_clientes_ruta)} clientes en esta ruta**")
                            
                            st.divider()
                            
                            for _, row_c in df_clientes_ruta.iterrows():
                                nombre = row_c['nombre_cliente']
                                telefono = str(row_c['telefono']).strip() if row_c['telefono'] else ""
                                
                                if telefono and validar_telefono(telefono):
                                    msg_prev = plantilla_preventa.replace("{nombre}", nombre).replace("{ruta}", ruta_notif_sel)
                                    msg_listo = plantilla_pedido_listo.replace("{nombre}", nombre).replace("{ruta}", ruta_notif_sel)
                                    
                                    col_c1, col_c2, col_c3 = st.columns([3, 1, 1])
                                    col_c1.write(f"👤 {nombre}")
                                    col_c1.caption(f"📱 {telefono}")
                                    col_c2.markdown(
                                        f'<a href="{enviar_whatsapp_link(telefono, msg_prev)}" target="_blank">'
                                        f'<button style="background-color:#FF9800;color:white;border:none;'
                                        f'padding:8px 12px;border-radius:5px;cursor:pointer;font-weight:bold;font-size:0.8rem;">'
                                        f'📅 Recordatorio</button></a>',
                                        unsafe_allow_html=True
                                    )
                                    col_c3.markdown(
                                        f'<a href="{enviar_whatsapp_link(telefono, msg_listo)}" target="_blank">'
                                        f'<button style="background-color:#4CAF50;color:white;border:none;'
                                        f'padding:8px 12px;border-radius:5px;cursor:pointer;font-weight:bold;font-size:0.8rem;">'
                                        f'📦 Listo</button></a>',
                                        unsafe_allow_html=True
                                    )
                                else:
                                    st.warning(f"⚠️ {nombre} — sin teléfono válido.")
                                    
                    except Exception as e:
                        st.error(f"❌ Error en preventa: {e}")

    # --- ADMINISTRADOR ---
    if seccion == "📊 Administrador":
        st.subheader("📊 Panel Administrador")
        streamlit_autorefresh.st_autorefresh(
            interval=15000,
            key="datarefresh"
        )
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se puede cargar el panel.")
        else:
            with get_db() as db:
                if db:
                    try:
                        df_base = pd.read_sql("SELECT * FROM pedidos", db)
                        
                        if not df_base.empty:
                            r_disp = sorted([r for r in df_base['ruta'].unique() if r and r != 'None'])
                            sel_admin = st.selectbox(
                                "Filtrar por Ruta:",
                                ["🌍 Todo"] + r_disp,
                                key="admin_ruta_filter"
                            )
                            
                            df_admin = df_base.copy() if sel_admin == "🌍 Todo" else df_base[df_base['ruta'] == sel_admin.strip()].copy()
                            
                            st.markdown("### ✏️ Editar Cliente")
                            
                            lista_clientes_edit = df_base.sort_values(by="nombre_cliente")
                            opciones_clientes = {
                                row['id']: f"{row['nombre_cliente']} ({row['ruta']})" 
                                for _, row in lista_clientes_edit.iterrows()
                            }
                            
                            id_seleccionado = st.selectbox(
                                "Cliente a editar:",
                                options=list(opciones_clientes.keys()),
                                format_func=lambda x: opciones_clientes[x],
                                key="cliente_editar_select"
                            )
                            
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button("🔍 Cargar para Edición", use_container_width=True):
                                    st.session_state.id_cliente_editar = id_seleccionado
                            
                            with col_btn2:
                                if st.button("🗑️ Eliminar Cliente", use_container_width=True):
                                    datos_elim = df_base[df_base['id'] == id_seleccionado].iloc[0]
                                    dialogo_eliminar_cliente(id_seleccionado, datos_elim['nombre_cliente'])
                            
                            if st.session_state.id_cliente_editar:
                                datos_c = df_base[df_base['id'] == st.session_state.id_cliente_editar].iloc[0]
                                
                                with st.form("formulario_edicion_cliente"):
                                    nuevo_nombre = st.text_input("Nombre:", value=datos_c['nombre_cliente'])
                                    nuevo_telefono = st.text_input("Teléfono:", value=datos_c['telefono'])
                                    nueva_ruta = st.text_input("Ruta:", value=datos_c['ruta'])
                                    nueva_referencia = st.text_area(
                                        "Referencias:",
                                        value=datos_c['referencia'],
                                        help="📷 Puedes incluir un link a una foto aquí"
                                    )
                                    nueva_cant_20 = st.number_input(
                                        "Garrafones 20L:",
                                        min_value=0,
                                        value=int(datos_c['cantidad_20L'])
                                    )
                                    nueva_cant_10 = st.number_input(
                                        "Garrafones 10L:",
                                        min_value=0,
                                        value=int(datos_c['cantidad_10L'])
                                    )
                                    
                                    if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                                        try:
                                            cursor_up = db.cursor()
                                            cursor_up.execute(
                                                """
                                                UPDATE pedidos 
                                                SET nombre_cliente=%s, telefono=%s, ruta=%s, 
                                                    referencia=%s, cantidad_20L=%s, cantidad_10L=%s 
                                                WHERE id=%s
                                                """,
                                                (nuevo_nombre, nuevo_telefono, nueva_ruta, 
                                                 nueva_referencia, nueva_cant_20, nueva_cant_10,
                                                 st.session_state.id_cliente_editar)
                                            )
                                            db.commit()
                                            cursor_up.close()
                                            st.success("✅ Datos actualizados correctamente.")
                                            st.session_state.id_cliente_editar = None
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Error al actualizar: {e}")
                            
                            st.divider()
                            
                            st.markdown("### 🔁 Reinicio de Rutas")
                            st.warning("⚠️ Úsala sólo al iniciar un nuevo día de reparto.")
                            
                            col_r1, col_r2 = st.columns(2)
                            with col_r1:
                                if st.button("🚨 REINICIAR TODAS LAS RUTAS", use_container_width=True, type="primary"):
                                    dialogo_reiniciar_todo()
                            
                            with col_r2:
                                ruta_a_reiniciar = st.selectbox(
                                    "Reiniciar una sola ruta:",
                                    ["-- Seleccionar --"] + r_disp,
                                    key="ruta_reinicio_individual"
                                )
                                if ruta_a_reiniciar != "-- Seleccionar --":
                                    if st.button(f"🔄 Reiniciar: {ruta_a_reiniciar}", use_container_width=True):
                                        dialogo_reiniciar_ruta(ruta_a_reiniciar)
                            
                            st.divider()
                            
                            st.markdown("### 📋 Tabla de Pedidos")
                            st.dataframe(df_admin, use_container_width=True)
                            
                            excel_data = exportar_excel(df_admin)
                            fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                            st.download_button(
                                label="📥 Exportar a Excel",
                                data=excel_data,
                                file_name=f"pedidos_viteg_{fecha_hoy}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"❌ Error en panel administrador: {e}")

    # --- REPORTES ---
    if seccion == "📈 Reportes":
        st.subheader("📈 Reportes y Análisis")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se pueden generar reportes.")
        else:
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
                            c4.metric(
                                "✅ Tasa de entrega", 
                                f"{int((entregados/total_clientes)*100)}%" if total_clientes > 0 else "0%"
                            )
                            
                            st.divider()
                            
                            df_por_ruta = df_rep.groupby('ruta').agg(
                                Clientes=('id', 'count'),
                                Garrafones_20L=('cantidad_20L', 'sum'),
                                Garrafones_10L=('cantidad_10L', 'sum'),
                                Entregados=('estatus', lambda x: (x == 'entregado').sum()),
                                Pendientes=('estatus', lambda x: (x == 'pendiente').sum()),
                                No_encontrados=('estatus', lambda x: (x == 'no encontrado').sum())
                            ).reset_index()
                            
                            st.dataframe(df_por_ruta, use_container_width=True)
                            
                            col_g1, col_g2 = st.columns(2)
                            with col_g1:
                                st.subheader("📊 Clientes por Ruta")
                                st.bar_chart(df_por_ruta.set_index('ruta')['Clientes'])
                            
                            with col_g2:
                                st.subheader("📊 Garrafones 20L por Ruta")
                                st.bar_chart(df_por_ruta.set_index('ruta')['Garrafones_20L'])
                            
                            st.divider()
                            
                            st.markdown("### 🚴 Garrafones entregados por Repartidor")
                            st.caption("💡 Usa el nombre de la **Ruta** como identificador del repartidor")
                            
                            df_entregados = df_rep[df_rep['estatus'] == 'entregado']
                            if not df_entregados.empty:
                                df_por_repartidor = df_entregados.groupby('ruta').agg(
                                    Pedidos_entregados=('id', 'count'),
                                    Garrafones_20L=('cantidad_20L', 'sum'),
                                    Garrafones_10L=('cantidad_10L', 'sum'),
                                ).reset_index().rename(columns={'ruta': 'Repartidor / Ruta'})
                                
                                df_por_repartidor['Total_garrafones'] = (
                                    df_por_repartidor['Garrafones_20L'] + 
                                    df_por_repartidor['Garrafones_10L']
                                )
                                df_por_repartidor = df_por_repartidor.sort_values(
                                    'Total_garrafones', 
                                    ascending=False
                                )
                                
                                st.dataframe(df_por_repartidor, use_container_width=True)
                                st.bar_chart(df_por_repartidor.set_index('Repartidor / Ruta')['Total_garrafones'])
                                
                                excel_repartidores = exportar_excel(df_por_repartidor)
                                st.download_button(
                                    label="📥 Exportar Ventas por Repartidor",
                                    data=excel_repartidores,
                                    file_name=f"repartidores_viteg_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True,
                                    key="btn_export_repartidores"
                                )
                            else:
                                st.info("ℹ️ Todavía no hay pedidos entregados.")
                            
                            st.divider()
                            
                            st.markdown("### 🏆 Top 10 Clientes por Garrafones")
                            df_rep['total_garrafones'] = df_rep['cantidad_20L'] + df_rep['cantidad_10L']
                            df_top = df_rep.nlargest(
                                10, 
                                'total_garrafones'
                            )[['nombre_cliente', 'ruta', 'cantidad_20L', 'cantidad_10L', 
                               'total_garrafones', 'estatus']]
                            st.dataframe(df_top, use_container_width=True)
                            
                            excel_reporte = exportar_excel(df_por_ruta)
                            st.download_button(
                                label="📥 Exportar Reporte Completo",
                                data=excel_reporte,
                                file_name=f"reporte_viteg_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        else:
                            st.info("ℹ️ No hay datos suficientes para generar reportes.")
                            
                    except Exception as e:
                        st.error(f"❌ Error en reportes: {e}")

# ==========================================
# RENDERIZADO REPARTIDOR
# ==========================================
else:
    
    # --- RUTA REPARTIDOR ---
    if seccion_rep == "🚚 Mi Ruta de Entrega":
        st.subheader("🚚 Mi Ruta de Entrega")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se puede cargar la ruta.")
        else:
            with get_db() as db:
                if db:
                    try:
                        df_chofer = pd.read_sql(
                            """
                            SELECT id, nombre_cliente, telefono, ruta, 
                                   cantidad_20L, cantidad_10L, referencia, 
                                   estatus, latitud, longitud 
                            FROM pedidos 
                            WHERE estatus != 'entregado'
                            """,
                            db
                        )
                        
                        if not df_chofer.empty:
                            rutas_chofer = sorted(list(df_chofer['ruta'].unique()))
                            ruta_sel = st.selectbox(
                                "Selecciona tu Ruta / Zona:",
                                rutas_chofer,
                                key="chofer_ruta_sel_rep"
                            )
                            
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
                                    df_todos = pd.read_sql(
                                        "SELECT estatus FROM pedidos WHERE ruta = %s",
                                        db2,
                                        params=(ruta_sel,)
                                    )
                                    entregados_hoy = len(df_todos[df_todos['estatus'] == 'entregado'])
                                    total_ruta_completa = len(df_todos)
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("📦 Pendientes", total_ruta)
                            c2.metric("✅ Entregados", entregados_hoy)
                            progreso = int((entregados_hoy / total_ruta_completa) * 100) if total_ruta_completa > 0 else 0
                            c3.metric("📊 Progreso", f"{progreso}%")
                            st.progress(progreso / 100)
                            st.divider()
                            
                            coords_validas = df_ruta_base[
                                (df_ruta_base['latitud'] != 0) & (df_ruta_base['longitud'] != 0)
                            ].copy()
                            sin_coords = df_ruta_base[
                                (df_ruta_base['latitud'] == 0) | (df_ruta_base['longitud'] == 0)
                            ].copy()
                            
                            col_opt1, col_opt2, col_opt3 = st.columns(3)
                            with col_opt1:
                                if st.button("🧭 OPTIMIZAR CON IA", use_container_width=True, type="primary", key="opt_rep"):
                                    if len(coords_validas) >= 2:
                                        df_optimizado = pd.concat([
                                            optimizar_ruta(coords_validas),
                                            sin_coords
                                        ]).reset_index(drop=True)
                                        st.session_state.df_ruta_ordenada = df_optimizado
                                        st.session_state.orden_manual = None
                                        st.session_state.ruta_optimizada = True
                                        st.session_state.modo_reordenar = False
                                        st.success("✅ Ruta optimizada por IA")
                                    else:
                                        st.warning("⚠️ Se necesitan al menos 2 clientes con GPS.")
                            
                            with col_opt2:
                                if st.button("✋ AJUSTAR MANUALMENTE", use_container_width=True, key="rea_rep"):
                                    st.session_state.modo_reordenar = True
                            
                            with col_opt3:
                                if st.button("↩️ Orden original", use_container_width=True, key="ori_rep"):
                                    st.session_state.ruta_optimizada = False
                                    st.session_state.df_ruta_ordenada = None
                                    st.session_state.orden_manual = None
                                    st.session_state.modo_reordenar = False
                            
                            if st.session_state.ruta_optimizada and st.session_state.df_ruta_ordenada is not None:
                                df_ruta_actual = st.session_state.df_ruta_ordenada.copy()
                            elif st.session_state.orden_manual is not None:
                                df_ruta_actual = st.session_state.orden_manual.copy()
                            else:
                                df_ruta_actual = df_ruta_base.copy()
                            
                            if st.session_state.modo_reordenar:
                                st.markdown("### ✋ Ajusta el orden manualmente")
                                
                                if ("lista_ids_manual" not in st.session_state or 
                                    st.session_state.lista_ids_ruta != ruta_sel):
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
                                    df_manual = df_ruta_actual.set_index('id').loc[
                                        st.session_state.lista_ids_manual
                                    ].reset_index()
                                    st.session_state.orden_manual = df_manual
                                    st.session_state.ruta_optimizada = False
                                    st.session_state.modo_reordenar = False
                                    st.rerun()
                                
                                st.divider()
                            
                            df_maps = df_ruta_actual[
                                (df_ruta_actual['latitud'] != 0) & (df_ruta_actual['longitud'] != 0)
                            ]
                            
                            if len(df_maps) > 1:
                                origen = f"{df_maps.iloc[0]['latitud']},{df_maps.iloc[0]['longitud']}"
                                destino = f"{df_maps.iloc[-1]['latitud']},{df_maps.iloc[-1]['longitud']}"
                                url_ruta_completa = f"https://www.google.com/maps/dir/{origen}/{destino}"
                                label = "🗺️ VER RUTA OPTIMIZADA" if st.session_state.ruta_optimizada else "🗺️ VER RUTA COMPLETA"
                                st.markdown(
                                    f'<a href="{url_ruta_completa}" target="_blank">'
                                    f'<button style="background-color:#34A853;color:white;border:none;'
                                    f'padding:12px;border-radius:5px;width:100%;cursor:pointer;'
                                    f'font-weight:bold;font-size:15px;margin-bottom:10px;">'
                                    f'{label}</button></a>',
                                    unsafe_allow_html=True
                                )
                            
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
                                        st.markdown(
                                            f'<a href="{foto_url}" target="_blank">📷 Ver foto de referencia</a>',
                                            unsafe_allow_html=True
                                        )
                                        try:
                                            st.image(foto_url, width=250)
                                        except:
                                            pass
                                    
                                    if row['latitud'] != 0 and row['longitud'] != 0:
                                        url_gmaps = f"https://www.google.com/maps/search/?api=1&query={row['latitud']},{row['longitud']}"
                                        st.markdown(
                                            f'<a href="{url_gmaps}" target="_blank">'
                                            f'<button style="background-color:#1a73e8;color:white;border:none;'
                                            f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                            f'🗺️ NAVEGAR</button></a>',
                                            unsafe_allow_html=True
                                        )
                                    
                                    if num_tel != "S/N" and validar_telefono(num_tel):
                                        c1, c2, c3 = st.columns(3)
                                        with c1:
                                            st.markdown(
                                                f'<a href="tel:{num_tel}">'
                                                f'<button style="background-color:#007BFF;color:white;border:none;'
                                                f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                                f'📞 LLAMAR</button></a>',
                                                unsafe_allow_html=True
                                            )
                                        with c2:
                                            msg_afuera = "Hola, le avisamos de Agua VITEG 💧. El camión ya está afuera. ¡Gracias!"
                                            st.markdown(
                                                f'<a href="{enviar_whatsapp_link(num_tel, msg_afuera)}" target="_blank">'
                                                f'<button style="background-color:#25D366;color:white;border:none;'
                                                f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                                f'📲 YA ESTOY AFUERA</button></a>',
                                                unsafe_allow_html=True
                                            )
                                        with c3:
                                            msg_ent = f"Hola {row['nombre_cliente']}, su pedido fue entregado. ¡Gracias!"
                                            st.markdown(
                                                f'<a href="{enviar_whatsapp_link(num_tel, msg_ent)}" target="_blank">'
                                                f'<button style="background-color:#128C7E;color:white;border:none;'
                                                f'padding:10px;border-radius:5px;width:100%;cursor:pointer;font-weight:bold;">'
                                                f'✅ CONFIRMAR</button></a>',
                                                unsafe_allow_html=True
                                            )
                                    
                                    st.markdown("---")
                                    
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        if st.button("✅ Marcar Entregado", key=f"ent_r_{row['id']}"):
                                            cursor = db.cursor()
                                            cursor.execute(
                                                "UPDATE pedidos SET estatus = 'entregado' WHERE id = %s",
                                                (row['id'],)
                                            )
                                            db.commit()
                                            cursor.close()
                                            st.session_state.ruta_optimizada = False
                                            st.session_state.df_ruta_ordenada = None
                                            st.rerun()
                                    
                                    with col_e2:
                                        if row['estatus'] != 'no encontrado':
                                            if st.button("❌ No Encontrado", key=f"noe_r_{row['id']}"):
                                                cursor = db.cursor()
                                                cursor.execute(
                                                    "UPDATE pedidos SET estatus = 'no encontrado' WHERE id = %s",
                                                    (row['id'],)
                                                )
                                                db.commit()
                                                cursor.close()
                                                st.rerun()
                        else:
                            st.success("🚚 ¡No hay pedidos pendientes!")
                            
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    # --- REGISTRO REPARTIDOR ---
    if seccion_rep == "📝 Registrar Cliente":
        st.subheader("📝 Registrar Cliente")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se puede registrar.")
        else:
            opciones_rutas_r = ["-- Escribir nueva ruta --"]
            with get_db() as db_rutas:
                if db_rutas:
                    try:
                        cursor_r = db_rutas.cursor()
                        cursor_r.execute("SELECT DISTINCT ruta FROM pedidos WHERE ruta IS NOT NULL AND ruta != ''")
                        for row_r in cursor_r.fetchall():
                            if row_r[0] not in opciones_rutas_r:
                                opciones_rutas_r.append(row_r[0])
                        cursor_r.close()
                    except:
                        pass
            
            st.markdown("### 🔍 Buscador de Clientes")
            busqueda_r = st.text_input("Buscar por nombre o teléfono:", key="busqueda_rep")
            
            if busqueda_r:
                with get_db() as db_bus:
                    if db_bus:
                        try:
                            df_bus = pd.read_sql(
                                """
                                SELECT id, nombre_cliente, telefono, ruta, referencia, estatus 
                                FROM pedidos 
                                WHERE nombre_cliente LIKE %s OR telefono LIKE %s
                                """,
                                db_bus,
                                params=(f"%{busqueda_r}%", f"%{busqueda_r}%")
                            )
                            if not df_bus.empty:
                                st.dataframe(df_bus, use_container_width=True)
                            else:
                                st.info("No se encontraron resultados.")
                        except:
                            st.warning("Error en la búsqueda")
            
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
                    tel_r = st.text_input("Teléfono:", help="Formato: 5551234567")
                    sel_ruta_r = st.selectbox("Ruta:", opciones_rutas_r)
                    rut_r = st.text_input("Nueva ruta:") if sel_ruta_r == "-- Escribir nueva ruta --" else sel_ruta_r
                    cant_20_r = st.number_input("Garrafones 20L:", min_value=0, value=0)
                    cant_10_r = st.number_input("Garrafones 10L:", min_value=0, value=0)
                
                with col_form2:
                    lat_f_r = st.number_input("Latitud:", value=lat_val_r, format="%.6f")
                    lon_f_r = st.number_input("Longitud:", value=lon_val_r, format="%.6f")
                    ref_r = st.text_area(
                        "Referencias:",
                        help="📷 Tip: puedes pegar aquí un link a una foto de la fachada",
                        height=100
                    )
                
                if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
                    if not nom_r or not nom_r.strip():
                        st.error("❌ El nombre del cliente es obligatorio")
                    elif not rut_r or not rut_r.strip():
                        st.error("❌ La ruta es obligatoria")
                    else:
                        with get_db() as db_alta:
                            if db_alta:
                                try:
                                    cursor_a = db_alta.cursor()
                                    cursor_a.execute(
                                        """
                                        INSERT INTO pedidos 
                                        (nombre_cliente, telefono, ruta, cantidad_20L, cantidad_10L, 
                                         referencia, estatus, latitud, longitud, direccion) 
                                        VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', %s, %s, '')
                                        """,
                                        (nom_r, tel_r, rut_r, cant_20_r, cant_10_r, ref_r, lat_f_r, lon_f_r)
                                    )
                                    db_alta.commit()
                                    cursor_a.close()
                                    st.success(f"🎉 '{nom_r}' registrado en ruta: {rut_r}")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")

    # --- PREVENTA REPARTIDOR ---
    if seccion_rep == "📲 Notificaciones de Preventa":
        st.subheader("📲 Notificaciones de Preventa")
        
        if not verificar_conexion_bd():
            st.error("❌ No hay conexión a la base de datos. No se pueden cargar los clientes.")
        else:
            plantilla_prev_r = st.text_area(
                "Plantilla recordatorio:",
                value="Hola {nombre}, le escribimos de Agua VITEG 💧. Mañana el camión pasará por su zona ({ruta}). ¡Nos vemos!",
                height=80,
                key="plantilla_prev_rep"
            )
            
            st.divider()
            
            with get_db() as db:
                if db:
                    try:
                        df_notif_r = pd.read_sql(
                            "SELECT nombre_cliente, telefono, ruta FROM pedidos",
                            db
                        )
                        
                        if not df_notif_r.empty:
                            rutas_notif_r = sorted([r.strip() for r in df_notif_r['ruta'].unique() if r])
                            ruta_notif_r = st.selectbox(
                                "Seleccionar Ruta:",
                                rutas_notif_r,
                                key="ruta_prev_rep"
                            )
                            
                            df_clientes_r = df_notif_r[df_notif_r['ruta'] == ruta_notif_r]
                            st.markdown(f"**👥 {len(df_clientes_r)} clientes**")
                            
                            st.divider()
                            
                            for _, row_c in df_clientes_r.iterrows():
                                nombre = row_c['nombre_cliente']
                                telefono = str(row_c['telefono']).strip() if row_c['telefono'] else ""
                                
                                if telefono and validar_telefono(telefono):
                                    msg = plantilla_prev_r.replace("{nombre}", nombre).replace("{ruta}", ruta_notif_r)
                                    
                                    col_c1, col_c2 = st.columns([3, 1])
                                    col_c1.write(f"👤 {nombre}")
                                    col_c1.caption(f"📱 {telefono}")
                                    col_c2.markdown(
                                        f'<a href="{enviar_whatsapp_link(telefono, msg)}" target="_blank">'
                                        f'<button style="background-color:#25D366;color:white;border:none;'
                                        f'padding:8px 12px;border-radius:5px;cursor:pointer;font-weight:bold;">'
                                        f'📲 Enviar</button></a>',
                                        unsafe_allow_html=True
                                    )
                                else:
                                    st.warning(f"⚠️ {nombre} — sin teléfono válido.")
                                    
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

# ==========================================
# FOOTER
# ==========================================
st.divider()
st.caption(f"💧 Agua VITEG - Sistema Logístico v2.0 | {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# Estado de la base de datos en el footer
if verificar_conexion_bd():
    st.caption("🟢 Base de datos: Conectada")
else:
    st.caption("🔴 Base de datos: Desconectada")

