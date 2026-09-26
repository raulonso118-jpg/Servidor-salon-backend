"""
Gestor de versiones de la aplicación NBO-A
Permite validar si el cliente tiene la versión correcta
"""
from datetime import datetime

# Versión actual de la aplicación
APP_VERSION_ACTUAL = "1.0.0"

# Versión mínima requerida para que funcione
VERSION_MINIMA_PERMITIDA = "1.0.0"

# Si está en True, fuerza a que todos actualicen
FORZAR_ACTUALIZACION = False

# Mensaje de actualización
MENSAJE_ACTUALIZACION = "Hay una nueva versión disponible con mejoras importantes"

def obtener_info_version():
    """
    Retorna información de la versión actual del servidor.
    Se usa para que el cliente chequee si necesita actualizar.
    """
    return {
        "version_actual": APP_VERSION_ACTUAL,
        "version_minima": VERSION_MINIMA_PERMITIDA,
        "forzar_actualizacion": FORZAR_ACTUALIZACION,
        "fecha_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mensaje": MENSAJE_ACTUALIZACION
    }

def validar_version(cliente_version):
    """
    Valida si la versión del cliente es compatible.
    
    Args:
        cliente_version: versión que envía el cliente (ej: "1.0.0")
    
    Returns:
        (bool, str): (es_válida, mensaje)
    """
    try:
        if not cliente_version:
            return False, "Versión no enviada"
        
        # Si es exactamente igual, está actualizado
        if cliente_version == APP_VERSION_ACTUAL:
            return True, "La versión es la actual"
        
        # Si el cliente tiene versión anterior
        if cliente_version < APP_VERSION_ACTUAL:
            if FORZAR_ACTUALIZACION:
                return False, f"Debes actualizar a la versión {APP_VERSION_ACTUAL}"
            else:
                return True, f"Hay una actualización disponible ({APP_VERSION_ACTUAL})"
        
        # Si el cliente tiene versión superior (dev version)
        if cliente_version > APP_VERSION_ACTUAL:
            return True, "Versión superior (probablemente en desarrollo)"
        
        return True, "Versión válida"
    
    except Exception as e:
        return False, f"Error al validar versión: {str(e)}"

def es_version_compatible(cliente_version):
    """
    Verifica si la versión mínima es cumplida.
    Retorna True si cliente_version >= VERSION_MINIMA_PERMITIDA
    """
    try:
        return cliente_version >= VERSION_MINIMA_PERMITIDA
    except:
        return False
