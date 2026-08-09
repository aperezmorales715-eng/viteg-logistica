import sqlite3
from contextlib import contextmanager
import pandas as pd
from datetime import datetime

# Nombre del archivo de la base de datos
DB_PATH = 'viteg.db'

@contextmanager
def get_db():
    """Context manager para conexiones a SQLite"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
    except Exception as e:
        print(f"Error de base de datos: {e}")
        yield None
    finally:
        if conn:
            conn.close()

def inicializar_bd():
    """Crea las tablas si no existen"""
    with get_db() as conn:
        if conn:
            # Crear tabla pedidos
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_cliente TEXT NOT NULL,
                    telefono TEXT,
                    ruta TEXT,
                    cantidad_20L INTEGER DEFAULT 0,
                    cantidad_10L INTEGER DEFAULT 0,
                    referencia TEXT,
                    estatus TEXT DEFAULT 'pendiente',
                    latitud REAL DEFAULT 0,
                    longitud REAL DEFAULT 0,
                    direccion TEXT,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Crear tabla logs (para auditoría)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT,
                    accion TEXT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            print("✅ Base de datos SQLite inicializada correctamente")

def registrar_accion_sqlite(usuario, accion):
    """Registra acciones en la tabla logs"""
    with get_db() as conn:
        if conn:
            try:
                conn.execute(
                    "INSERT INTO logs (usuario, accion, fecha) VALUES (?, ?, ?)",
                    (usuario, accion, datetime.now())
                )
                conn.commit()
            except:
                pass

# Inicializar la base de datos al importar
inicializar_bd()

Agregar database.py para SQLite
