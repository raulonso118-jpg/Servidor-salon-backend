"""
Validador de licencias seguro con hash criptográfico.
Genera, valida y verifica licencias contra la base de datos.
"""
import os
import hashlib
import hmac
import random
import string
from datetime import datetime, timedelta
from db_manager import (
    obtener_licencia,
    guardar_licencia,
    actualizar_uso_licencia,
    registrar_validacion,
    registrar_log,
)

# Configuración por entorno (NO hardcodear secretos en producción)
DEV_MODO_ACTIVO = os.environ.get("DEV_MODE", "false").strip().lower() == "true"
DEV_LICENCIA_MAESTRA = os.environ.get("DEV_LICENCIA_MAESTRA", "GEN-DEV-MASTER-2026")
DEV_API_KEY = os.environ.get("DEV_API_KEY", "")
DEV_TOKEN = os.environ.get("DEV_TOKEN", "")

# Secret para firmar licencias
SECRET_SEED = os.environ.get("LIC_SECRET_SEED", "CAMBIAR_EN_PRODUCCION")


def _generar_random_code(longitud=6):
    """Genera código aleatorio para la licencia."""
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(longitud))


def _calcular_hash(codigo, secret=SECRET_SEED):
    """Calcula hash SHA256 de una licencia."""
    texto = f"{codigo}:{secret}"
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _firma_habilitada():
    """Las licencias firmadas solo se emiten si hay un secreto propio configurado."""
    return SECRET_SEED not in ("", "CAMBIAR_EN_PRODUCCION")


def _firmar(cuerpo):
    return hmac.new(SECRET_SEED.encode("utf-8"), cuerpo.encode("utf-8"), hashlib.sha256).hexdigest()[:12].upper()


def _validar_firmada(codigo):
    """
    Valida GEN-<YYYYMMDD expiración>-<RANDOM6>-<FIRMA12> sin consultar la BD.
    Retorna None si el código no tiene formato firmado; si lo tiene, (ok, mensaje, días).
    """
    partes = codigo.split("-")
    if len(partes) != 4 or not (len(partes[1]) == 8 and partes[1].isdigit()):
        return None
    if not _firma_habilitada():
        return False, "Licencias firmadas no disponibles: falta LIC_SECRET_SEED", 0
    cuerpo = "-".join(partes[:3])
    if not hmac.compare_digest(_firmar(cuerpo), partes[3].upper()):
        return False, "Licencia modificada o corrupta (firma no válida)", 0
    try:
        fecha_exp = datetime.strptime(partes[1], "%Y%m%d").date()
    except ValueError:
        return False, "Licencia inválida", 0
    dias_restantes = (fecha_exp - datetime.now().date()).days
    if dias_restantes < 0:
        return False, f"Licencia expirada el {fecha_exp.isoformat()}", 0
    return True, f"Licencia activa. Restan {dias_restantes} días.", dias_restantes


def _fecha_hoy():
    """Retorna fecha actual en formato YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def _fecha_ahora():
    """Retorna datetime actual en formato YYYY-MM-DD HH:MM:SS."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _calcular_expiracion(dias=30):
    """Calcula fecha de expiración sumando días a hoy."""
    fecha_exp = datetime.now() + timedelta(days=dias)
    return fecha_exp.strftime("%Y-%m-%d")


def _validar_formato_fecha(fecha_str):
    """Valida si una fecha en formato YYYY-MM-DD es válida."""
    try:
        datetime.strptime(fecha_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def generar_licencia_real(dias=30, email="cliente@salon.com", device_id=None):
    """
    Genera una licencia comercial nueva y la guarda en BD.

    Retorna: {
        "codigo": "GEN-2026-09-26-A7F4K2",
        "email": "cliente@salon.com",
        "fecha_inicio": "2026-09-26",
        "fecha_expiracion": "2026-10-26",
        "dias": 30,
        "hash": "sha256_hash"
    }
    """
    fecha_inicio = _fecha_hoy()
    fecha_expiracion = _calcular_expiracion(dias)
    firmada = _firma_habilitada()
    if firmada:
        cuerpo = f"GEN-{fecha_expiracion.replace('-', '')}-{_generar_random_code(6)}"
        codigo = f"{cuerpo}-{_firmar(cuerpo)}"
    else:
        codigo = f"GEN-{fecha_inicio}-{_generar_random_code(6)}"
    hash_code = _calcular_hash(codigo)

    # Guardar en BD
    guardada = guardar_licencia(
        codigo=codigo,
        email=email,
        fecha_inicio=fecha_inicio,
        fecha_expiracion=fecha_expiracion,
        hash_code=hash_code,
        device_id=device_id
    )

    # Una licencia firmada es válida aunque la BD (SQLite efímera) falle o se pierda
    if guardada or firmada:
        registrar_log("generar_licencia", f"Licencia creada: {codigo} para {email}")
        return {
            "codigo": codigo,
            "email": email,
            "fecha_inicio": fecha_inicio,
            "fecha_expiracion": fecha_expiracion,
            "dias": dias,
            "hash": hash_code,
            "estatus": "ok"
        }
    else:
        return {"estatus": "error", "mensaje": "Error al guardar licencia en BD"}


def validar_licencia_desarrollador(licencia, api_key=None, token=None):
    """
    Valida si es la licencia maestra de desarrollo.

    Retorna: (bool, str) - (es_válida, mensaje)
    """
    if not DEV_MODO_ACTIVO:
        return False, "Modo desarrollador desactivado"

    if not licencia:
        return False, "Licencia vacía"

    # Licencia maestra exacta
    if DEV_LICENCIA_MAESTRA and licencia == DEV_LICENCIA_MAESTRA:
        registrar_log("validar_dev", "Licencia DEV aceptada")
        return True, "Licencia de desarrollador válida"

    # Validación por API key
    if DEV_API_KEY and api_key and api_key == DEV_API_KEY:
        registrar_log("validar_api_key", f"API key válida: {api_key[:10]}...")
        return True, "API key de desarrollador válida"

    # Validación por token
    if DEV_TOKEN and token and token == DEV_TOKEN:
        registrar_log("validar_token", "Token válido")
        return True, "Token de desarrollador válido"

    return False, "Credenciales de desarrollador inválidas"


def validar_licencia_real(licencia_codigo, dispositivo=None, ip=None):
    """
    Valida una licencia comercial real contra la BD.

    Verifica:
    1. Formato correcto
    2. Existe en BD
    3. Hash es válido
    4. No ha expirado
    5. Está activa

    Retorna: (bool, str, int) - (es_válida, mensaje, días_restantes)
    """
    if not licencia_codigo:
        return False, "Licencia vacía", 0

    licencia_codigo = licencia_codigo.strip()

    # Primero: validación de desarrollador
    if DEV_MODO_ACTIVO and DEV_LICENCIA_MAESTRA and licencia_codigo == DEV_LICENCIA_MAESTRA:
        registrar_validacion(licencia_codigo, dispositivo, "valida_dev", ip)
        return True, "Licencia de desarrollo válida", 999

    # Segundo: validar formato
    if not licencia_codigo.startswith("GEN-"):
        registrar_validacion(licencia_codigo, dispositivo, "formato_invalido", ip)
        registrar_log("validacion_fallida", f"Formato inválido: {licencia_codigo}")
        return False, "Formato de licencia inválido. Debe comenzar con GEN-", 0

    # Licencias firmadas: se validan sin depender de la BD
    firmada = _validar_firmada(licencia_codigo)
    if firmada is not None:
        ok, mensaje, dias = firmada
        resultado_bd = obtener_licencia(licencia_codigo)
        if ok and resultado_bd and not resultado_bd[5]:
            ok, mensaje, dias = False, "Esta licencia ha sido desactivada", 0
        registrar_validacion(licencia_codigo, dispositivo, "valida" if ok else "firma_o_expirada", ip)
        if not ok:
            registrar_log("validacion_fallida", f"{mensaje}: {licencia_codigo}")
        return ok, mensaje, dias

    # Tercero: obtener de BD
    resultado_bd = obtener_licencia(licencia_codigo)
    if not resultado_bd:
        registrar_validacion(licencia_codigo, dispositivo, "no_encontrada", ip)
        registrar_log("validacion_fallida", f"Licencia no encontrada en BD: {licencia_codigo}")
        return False, "Licencia no registrada en el sistema", 0

    codigo, email, hash_almacenado, fecha_inicio, fecha_expiracion, activa, usos, device_id = resultado_bd

    # Cuarto: validar hash
    hash_calculado = _calcular_hash(codigo)
    if hash_calculado != hash_almacenado:
        registrar_validacion(codigo, dispositivo, "hash_invalido", ip)
        registrar_log("validacion_fallida", f"Hash inválido para: {codigo}")
        return False, "Licencia modificada o corrupta (hash no válido)", 0

    # Quinto: validar que esté activa
    if not activa:
        registrar_validacion(codigo, dispositivo, "licencia_desactivada", ip)
        registrar_log("validacion_fallida", f"Licencia desactivada: {codigo}")
        return False, "Esta licencia ha sido desactivada", 0

    # Sexto: validar fecha de expiración
    try:
        fecha_exp = datetime.strptime(fecha_expiracion, "%Y-%m-%d").date()
        hoy = datetime.now().date()
        dias_restantes = (fecha_exp - hoy).days

        if hoy > fecha_exp:
            registrar_validacion(codigo, dispositivo, "expirada", ip)
            registrar_log("validacion_fallida", f"Licencia expirada: {codigo}")
            return False, f"Licencia expirada el {fecha_expiracion}", 0

        # ¡Licencia válida!
        actualizar_uso_licencia(codigo)
        registrar_validacion(codigo, dispositivo, "valida", ip)
        registrar_log("validacion_exitosa", f"Licencia válida: {codigo} por {email}")

        return True, f"Licencia activa. Restan {dias_restantes} días.", dias_restantes

    except Exception as e:
        registrar_validacion(codigo, dispositivo, "error_validacion", ip)
        registrar_log("validacion_fallida", f"Error validando fecha: {str(e)}")
        return False, f"Error validando licencia: {str(e)}", 0


def validar_licencia_completa(licencia_codigo, api_key=None, token=None, dispositivo=None, ip=None):
    """
    Validación completa: primero intenta dev, luego real.
    Esta es la función que debe usar el servidor.

    Retorna: (bool, str, int) - (es_válida, mensaje, días_restantes)
    """
    if not licencia_codigo:
        return False, "No se envió licencia", 0

    # Intenta validación de desarrollador
    ok_dev, msg_dev = validar_licencia_desarrollador(licencia_codigo, api_key, token)
    if ok_dev:
        return True, msg_dev, 999

    # Intenta validación real
    ok_real, msg_real, dias = validar_licencia_real(licencia_codigo, dispositivo, ip)
    return ok_real, msg_real, dias
