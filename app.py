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
from scipy.spatial.distance import cdist

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(page_title="Sistema Interno - Agua VITEG", layout="wide")

# ==========================================
# LOGIN
# ==========================================
CLAVE_ADMIN = "viteg2024"
CLAVE_REPARTIDOR = "reparto123"

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

