import os
import uuid
import requests
import mercadopago

PLANES = {
    "semanal": {"precio": 39.0, "dias": 7, "titulo": "Licencia Semanal NBO-A"},
    "mensual": {"precio": 119.0, "dias": 30, "titulo": "Licencia Mensual NBO-A"},
    "anual": {"precio": 999.0, "dias": 365, "titulo": "Licencia Anual NBO-A"},
}


def _get_access_token():
    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError("Falta MP_ACCESS_TOKEN en variables de entorno")
    return token


def _get_base_url():
    base = os.environ.get("APP_BASE_URL", "").strip()
    if not base:
        raise ValueError("Falta APP_BASE_URL en variables de entorno")
    return base.rstrip("/")


def obtener_plan(plan: str):
    if not plan:
        raise ValueError("No se envió plan")
    clave = plan.strip().lower()
    if clave not in PLANES:
        raise ValueError("Plan inválido. Usa: semanal, mensual, anual")
    return clave, PLANES[clave]


def crear_preferencia(email: str, plan: str):
    if not email or "@" not in email:
        raise ValueError("Email inválido")

    plan_key, plan_data = obtener_plan(plan)
    token = _get_access_token()
    base_url = _get_base_url()

    sdk = mercadopago.SDK(token)
    external_reference = f"orden_{plan_key}_{uuid.uuid4().hex[:16]}"

    body = {
        "items": [
            {
                "title": plan_data["titulo"],
                "quantity": 1,
                "currency_id": "MXN",
                "unit_price": float(plan_data["precio"]),
            }
        ],
        "payer": {"email": email},
        "external_reference": external_reference,
        "notification_url": f"{base_url}/api/pagos/webhook",
        "back_urls": {
            "success": f"{base_url}/pago-exito",
            "failure": f"{base_url}/pago-fallo",
            "pending": f"{base_url}/pago-pendiente",
        },
        "auto_return": "approved",
        "metadata": {
            "email": email,
            "plan": plan_key,
            "dias_licencia": int(plan_data["dias"]),
        },
    }

    resp = sdk.preference().create(body)
    data = resp.get("response", {}) if isinstance(resp, dict) else {}

    init_point = data.get("init_point")
    pref_id = data.get("id")

    if not init_point or not pref_id:
        raise ValueError(f"No se pudo crear preferencia MP: {resp}")

    return {
        "init_point": init_point,
        "preference_id": pref_id,
        "external_reference": external_reference,
        "plan": plan_key,
        "precio": plan_data["precio"],
        "dias": plan_data["dias"],
    }


def obtener_pago(payment_id: str):
    token = _get_access_token()
    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code >= 400:
        raise ValueError(f"Error consultando pago MP: {r.status_code} {r.text}")
    return r.json()


def extraer_data_pago(pago_json: dict):
    status = str(pago_json.get("status", "")).lower()
    payer = pago_json.get("payer") or {}
    metadata = pago_json.get("metadata") or {}
    external_reference = pago_json.get("external_reference")
    payment_id = str(pago_json.get("id", ""))

    email = payer.get("email") or metadata.get("email")
    plan = (metadata.get("plan") or "").lower()

    if plan not in PLANES:
        plan = "mensual"  # fallback seguro

    dias = int(PLANES[plan]["dias"])

    return {
        "payment_id": payment_id,
        "status": status,
        "email": email,
        "plan": plan,
        "dias": dias,
        "external_reference": external_reference,
    }


def buscar_pago_aprobado(external_reference: str):
    """Devuelve el id del pago aprobado de una orden, o None."""
    token = _get_access_token()
    r = requests.get(
        "https://api.mercadopago.com/v1/payments/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"external_reference": external_reference, "status": "approved", "limit": 1},
        timeout=20,
    )
    if r.status_code >= 400:
        raise ValueError(f"Error buscando pago MP: {r.status_code}")
    resultados = r.json().get("results") or []
    return str(resultados[0]["id"]) if resultados else None
