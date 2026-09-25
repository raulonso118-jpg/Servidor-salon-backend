import hashlib
import os
import random
import string
from datetime import datetime, timedelta

# ------------------------------
# CONFIGURACIÓN DE DESARROLLADOR
# ------------------------------
DEV_MODO_ACTIVO = True
DEV_LICENCIA_MAESTRA = "GEN-DEV-MASTER-2026"
DEV_API_KEY = "sk_dev_salon_nboa_2026_secret_key"
DEV_TOKEN = "dev_token_123456789"

# ------------------------------
# FUNCIONES AUXILIARES
# ------------------------------
def generar_random_code(longitud=6):
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(longitud))


def sha256(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def fecha_hoy():
    return datetime.now().strftime("%Y-%m-%d")


def fecha_ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calcular_expiracion(dias=30):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")


def validar_formato_fecha(fecha_str):
    try:
        datetime.strptime(fecha_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ------------------------------
# LICENCIA DE DESARROLLADOR
# ------------------------------
def generar_licencia_desarrollador():
    """
    Genera una licencia de desarrollador que debe permitirse en pruebas.
    Formato de ejemplo:
        GEN-DEV-2026-09-25-A7F4K2
    """
    fecha = fecha_hoy().replace("-", "-")
    codigo = f"GEN-DEV-{fecha}-{generar_random_code(6)}"
    return codigo


def validar_licencia_desarrollador(licencia, api_key=None, token=None):
    """
    Valida si la licencia es la maestra de desarrollador.
    Retorna: (bool, mensaje)
    """
    if not DEV_MODO_ACTIVO:
        return False, "Modo desarrollador desactivado"

    if not licencia:
        return False, "Licencia vacía"

    if licencia == DEV_LICENCIA_MAESTRA:
        return True, "Licencia de desarrollador válida"

    if licencia == generar_licencia_desarrollador():
        # Esto casi nunca será igual, pero lo dejamos solo como prevención
        return False, "Licencia de desarrollador no autorizada"

    # validación por API key/token
    if api_key and api_key == DEV_API_KEY:
        return True, "API key de desarrollador válida"

    if token and token == DEV_TOKEN:
        return True, "Token de desarrollador válido"

    return False, "Licencia de desarrollador inválida"


# ------------------------------
# LICENCIA NORMAL (REAL)
# ------------------------------
def generar_licencia_real(dias=30):
    """
    Genera una licencia comercial con fecha de expiración.
    Formato:
        GEN-2026-09-25-A7F4K2
    """
    fecha = fecha_hoy()
    codigo = f"GEN-{fecha}-{generar_random_code(6)}"
    return {
        "codigo": codigo,
        "fecha_inicio": fecha,
        "fecha_expiracion": calcular_expiracion(dias),
        "dias": dias,
        "hash": sha256(codigo),
    }


def validar_licencia_real(licencia_codigo, fecha_expiracion=None):
    """
    Valida si una licencia real sigue vigente.
    Retorna: (bool, mensaje, dias_restantes)
    """
    if not licencia_codigo:
        return False, "Licencia vacía", 0

    # Si es una licencia de desarrollador, se acepta si DEV_MODO_ACTIVO=True
    if DEV_MODO_ACTIVO and licencia_codigo == DEV_LICENCIA_MAESTRA:
        return True, "Licencia de desarrollo válida", 999

    if not licencia_codigo.startswith("GEN-"):
        return False, "Formato de licencia inválido", 0

    partes = licencia_codigo.split("-")
    if len(partes) < 4:
        return False, "Estructura de licencia inválida", 0

    # Busca fecha en formato YYYY-MM-DD dentro del código.
    fecha_exp = None
    for i in range(len(partes) - 2):
        try:
            fecha = f"{partes[i]}-{partes[i+1]}-{partes[i+2]}"
            if validar_formato_fecha(fecha):
                fecha_exp = fecha
                break
        except Exception:
            pass

    if not fecha_exp:
        if "DEV" in licencia_codigo.upper():
            return True, "Licencia de prueba válida", 999
        return False, "La licencia no incluye fecha válida", 0

    if fecha_expiracion:
        fecha_ex = fecha_expiracion
    else:
        fecha_ex = fecha_exp

    try:
        fecha_obj = datetime.strptime(fecha_ex, "%Y-%m-%d").date()
        hoy = datetime.now().date()
        restante = (fecha_obj - hoy).days

        if hoy <= fecha_obj:
            return True, f"Licencia activa. Restan {restante} días.", restante
        return False, "La licencia ha expirado", 0
    except Exception as e:
        return False, f"Error validando fecha: {str(e)}", 0


# ------------------------------
# PROBADOR DE CÓDIGO
# ------------------------------
def main():
    print("=== LICENCIAS NBO-A ===")
    print("Modo desarrollador:", DEV_MODO_ACTIVO)
    print("Licencia maestra:", DEV_LICENCIA_MAESTRA)
    print("")

    accion = input("¿Qué quieres hacer? [g=generar licencia dev, v=validar licencia, q=salir]: ").strip().lower()

    if accion == "g":
        code = generar_licencia_desarrollador()
        print("Licencia generada:", code)

    elif accion == "v":
        code = input("Escribe la licencia a validar: ").strip()
        ok, mensaje = validar_licencia_desarrollador(code)
        print("Resultado:", ok, mensaje)

    else:
        print("Saliendo...")


if __name__ == "__main__":
    main()
