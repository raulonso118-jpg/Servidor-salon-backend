"""
Configuración centralizada del servidor NBO-A
"""
import os
from datetime import datetime, timedelta

# ==================== SERVIDOR ====================
PORT = int(os.environ.get("PORT", 8080))
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
AMBIENTE = os.environ.get("AMBIENTE", "desarrollo")  # desarrollo, produccion

# ==================== BASE DE DATOS ====================
DB_PATH = os.environ.get("DB_PATH", "salon_licencias.db")
DB_BACKUP = os.environ.get("DB_BACKUP", "salon_licencias.backup.db")

# ==================== LICENCIAS ====================
# Formato de licencia: GEN-YYYY-MM-DD-XXXXXX
LICENCIA_PREFIX = "GEN"
LICENCIA_LENGTH = 6  # XXXXXX = 6 caracteres aleatorios

# Duraciones disponibles (en días)
DURACIONES = {
    "prueba": 7,      # Prueba gratis
    "30": 30,         # Licencia 30 días
    "90": 90,         # Licencia 90 días
    "365": 365        # Licencia anual
}

# ==================== LICENCIA DE DESARROLLADOR ====================
# Esta es TU licencia para pruebas sin restricciones
DEV_MODO_ACTIVO = True
DEV_LICENCIA_MAESTRA = os.environ.get("DEV_LICENCIA", "GEN-DEV-MASTER-2026")
DEV_API_KEY = os.environ.get("DEV_API_KEY", "sk_dev_salon_nboa_2026_secret_key")
DEV_TOKEN = os.environ.get("DEV_TOKEN", "dev_token_123456789")

# ==================== MOTOR NBO-A ====================
MOTOR_NOMBRE = "NBO-A Génesis B"
MOTOR_VERSION = "1.0.0"
SECRET_SEED = os.environ.get("SECRET_SEED", "GENESIS_B_SECRET_2026")

# ==================== MERCADO PAGO (Futuro) ====================
MERCADOPAGO_ACCESS_TOKEN = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "")
MERCADOPAGO_PUBLIC_KEY = os.environ.get("MERCADOPAGO_PUBLIC_KEY", "")
MERCADOPAGO_WEBHOOK_TOKEN = os.environ.get("MERCADOPAGO_WEBHOOK_TOKEN", "")

# ==================== PRECIOS ====================
PRECIOS = {
    "prueba": 0.00,      # Gratis
    "30": 9.99,          # $9.99 por 30 días
    "90": 24.99,         # $24.99 por 90 días
    "365": 79.99         # $79.99 por 1 año
}

# ==================== SECURITY ====================
VALIDACIONES_MAX_POR_DIA = 100  # Máximo de validaciones por dispositivo/día
INTENTOS_FALLIDOS_MAX = 5  # Máximo de intentos fallidos antes de bloquear
BLOQUEO_DURACION_MINUTOS = 15  # Tiempo de bloqueo tras múltiples intentos

# ==================== LOGS ====================
LOG_PATH = os.environ.get("LOG_PATH", "logs/")
LOG_NIVEL = os.environ.get("LOG_NIVEL", "INFO")

# ==================== FUNCIONES AUXILIARES ====================
def obtener_fecha_hoy():
    """Retorna fecha actual en formato YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")

def obtener_datetime_ahora():
    """Retorna datetime actual en formato YYYY-MM-DD HH:MM:SS"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calcular_fecha_expiracion(dias):
    """Calcula fecha de expiración sumando días a hoy"""
    fecha_exp = datetime.now() + timedelta(days=dias)
    return fecha_exp.strftime("%Y-%m-%d")

def es_fecha_valida(fecha_str):
    """Verifica si una fecha en formato YYYY-MM-DD es válida y no ha pasado"""
    try:
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        hoy = datetime.now().date()
        return fecha_obj >= hoy
    except:
        return False

def dias_restantes(fecha_exp_str):
    """Calcula cuántos días faltan para la expiración"""
    try:
        fecha_exp = datetime.strptime(fecha_exp_str, "%Y-%m-%d").date()
        hoy = datetime.now().date()
        diferencia = (fecha_exp - hoy).days
        return max(0, diferencia)
    except:
        return 0
