"""
Gestor de base de datos SQLite para licencias y validaciones.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "salon_licencias.db")


def init_db():
    """Inicializa la base de datos con tablas de licencias."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Tabla de usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    nombre TEXT,
                    fecha_registro TEXT NOT NULL,
                    activo BOOLEAN DEFAULT 1
                )
            ''')
            
            # Tabla de licencias (la más importante)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS licencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT UNIQUE NOT NULL,
                    usuario_id INTEGER,
                    email TEXT,
                    device_id TEXT,
                    hash TEXT NOT NULL,
                    fecha_inicio TEXT NOT NULL,
                    fecha_expiracion TEXT NOT NULL,
                    tipo_duracion INTEGER DEFAULT 30,
                    activa BOOLEAN DEFAULT 1,
                    fecha_creacion TEXT NOT NULL,
                    fecha_validacion_ultima TEXT,
                    usos INTEGER DEFAULT 0,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
                )
            ''')
            
            # Tabla de validaciones (auditoría)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS validaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    licencia_codigo TEXT NOT NULL,
                    dispositivo TEXT,
                    fecha_validacion TEXT NOT NULL,
                    resultado TEXT,
                    ip_cliente TEXT,
                    FOREIGN KEY (licencia_codigo) REFERENCES licencias (codigo)
                )
            ''')
            
            # Tabla de logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    detalles TEXT,
                    fecha TEXT NOT NULL,
                    ip TEXT
                )
            ''')
            
            conn.commit()
            print("✅ Base de datos inicializada correctamente.")
    except sqlite3.Error as e:
        print(f"❌ Error al inicializar DB: {e}")


def guardar_licencia(codigo, email, fecha_inicio, fecha_expiracion, hash_code, device_id=None):
    """Guarda una nueva licencia en la base de datos."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO licencias 
                (codigo, email, hash, fecha_inicio, fecha_expiracion, 
                 fecha_creacion, device_id, activa)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (codigo, email, hash_code, fecha_inicio, fecha_expiracion, 
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device_id))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        print(f"⚠️ Licencia duplicada: {codigo}")
        return False
    except sqlite3.Error as e:
        print(f"❌ Error guardando licencia: {e}")
        return False


def obtener_licencia(codigo):
    """Obtiene una licencia de la base de datos."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT codigo, email, hash, fecha_inicio, fecha_expiracion, 
                       activa, usos, device_id
                FROM licencias WHERE codigo = ?
            ''', (codigo,))
            result = cursor.fetchone()
            return result
    except sqlite3.Error as e:
        print(f"❌ Error obteniendo licencia: {e}")
        return None


def registrar_validacion(codigo, dispositivo, resultado, ip):
    """Registra un intento de validación en auditoría."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO validaciones 
                (licencia_codigo, dispositivo, fecha_validacion, resultado, ip_cliente)
                VALUES (?, ?, ?, ?, ?)
            ''', (codigo, dispositivo, 
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                  resultado, ip))
            conn.commit()
    except sqlite3.Error as e:
        print(f"⚠️ Error registrando validación: {e}")


def actualizar_uso_licencia(codigo):
    """Incrementa el contador de usos y actualiza fecha de validación."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE licencias 
                SET usos = usos + 1, 
                    fecha_validacion_ultima = ?
                WHERE codigo = ?
            ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), codigo))
            conn.commit()
    except sqlite3.Error as e:
        print(f"⚠️ Error actualizando uso: {e}")


def registrar_log(tipo, detalles, ip=None):
    """Registra eventos en el log del servidor."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (tipo, detalles, fecha, ip)
                VALUES (?, ?, ?, ?)
            ''', (tipo, detalles, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ip))
            conn.commit()
    except sqlite3.Error as e:
        print(f"⚠️ Error registrando log: {e}")
