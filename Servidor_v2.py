"""Servidor HTTP del backend NBO-A con validación de licencias y pagos MP."""
import base64
import datetime
import hashlib
import hmac
import html
import http.server
import io
import json
import os
import socketserver
import threading
from urllib.parse import parse_qs, urlparse

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from db_manager import init_db
from validador_licencias import validar_licencia_completa, generar_licencia_real
from pagos_mp import crear_preferencia, obtener_pago, extraer_data_pago
from pagos_db import init_pagos_db, obtener_pago_guardado, guardar_pago

PORT = int(os.environ.get("PORT", 8080))
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Evita generar dos licencias si llegan notificaciones simultáneas del mismo pago
PAGOS_LOCK = threading.Lock()

init_db()
init_pagos_db()


def procesar_pago(payment_id, external_reference=None):
    """Consulta el pago en Mercado Pago y, si está aprobado, genera la licencia una sola vez."""
    with PAGOS_LOCK:
        guardado = obtener_pago_guardado(payment_id)
        if guardado:
            if external_reference and guardado["external_reference"] != external_reference:
                raise ValueError("La referencia no coincide con el pago")
            return {"status": "approved", "procesado": True, **guardado}

        pago = extraer_data_pago(obtener_pago(payment_id))
        if external_reference and pago["external_reference"] != external_reference:
            raise ValueError("La referencia no coincide con el pago")
        if pago["status"] != "approved":
            return {"status": pago["status"], "procesado": False}
        if not str(pago.get("external_reference") or "").startswith("orden_"):
            raise ValueError("El pago no pertenece a una orden de licencia")

        email = pago.get("email") or "cliente@salon.com"
        dias = int(pago["dias"])
        licencia = generar_licencia_real(dias=dias, email=email, device_id=None)
        if licencia.get("estatus") != "ok":
            raise RuntimeError("No se pudo generar la licencia")

        guardar_pago(payment_id, pago["external_reference"], email, pago["plan"], dias, licencia["codigo"])
        return {
            "status": "approved",
            "procesado": True,
            "payment_id": str(payment_id),
            "external_reference": pago["external_reference"],
            "email": email,
            "plan": pago["plan"],
            "dias": dias,
            "licencia": licencia["codigo"],
        }


def firma_webhook_valida(headers, data_id):
    """Si MP envía x-signature y hay MP_WEBHOOK_SECRET, la firma debe ser válida."""
    secret = os.environ.get("MP_WEBHOOK_SECRET", "").strip()
    firma = headers.get("x-signature", "")
    if not secret or not firma:
        return True
    partes = {}
    for parte in firma.split(","):
        if "=" in parte:
            k, v = parte.split("=", 1)
            partes[k.strip()] = v.strip()
    manifest = f"id:{str(data_id).lower()};request-id:{headers.get('x-request-id', '')};ts:{partes.get('ts', '')};"
    esperado = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, partes.get("v1", ""))


def pagina_html(titulo, mensaje, licencia=None):
    bloque = ""
    if licencia:
        bloque = (
            "<p>Tu licencia (guárdala):</p>"
            f"<p style='font-size:24px;font-weight:bold;word-break:break-all'>{html.escape(licencia)}</p>"
        )
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(titulo)}</title></head>"
        "<body style='font-family:sans-serif;max-width:480px;margin:40px auto;padding:0 16px'>"
        f"<h1>{html.escape(titulo)}</h1><p>{html.escape(mensaje)}</p>{bloque}</body></html>"
    ).encode("utf-8")


def respuesta(handler, payload, status=200):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(data)


def respuesta_html(handler, contenido, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(contenido)))
    handler.end_headers()
    handler.wfile.write(contenido)


def licencia_autorizada(handler, datos):
    ok, mensaje, _dias = validar_licencia_completa(
        datos.get("licencia", ""),
        api_key=datos.get("api_key"),
        token=datos.get("token"),
        dispositivo=datos.get("device_id"),
        ip=handler.client_address[0],
    )
    if not ok:
        respuesta(handler, {"estatus": "error", "mensaje": mensaje, "dias_restantes": 0}, 403)
        return False
    return True


def cargar_imagen(datos, *nombres):
    valor = next((datos.get(nombre) for nombre in nombres if datos.get(nombre)), None)
    if not valor:
        raise ValueError("No se envió imagen")
    encoded = valor.split(",", 1)[1] if "," in valor else valor
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen supera el límite permitido de 10 MB")
    return Image.open(io.BytesIO(raw)).convert("RGB")


def procesar_rostro(img, datos):
    arr = np.asarray(img, dtype=np.float32)
    brillo = float(datos.get("brillo", 100)) / 100.0
    contraste = float(datos.get("contraste", 100)) / 100.0
    arr = (arr - 128.0) * contraste + 128.0 + ((brillo - 1.0) * 50.0)

    modo = datos.get("modo_color", "normal")
    if modo == "gris":
        gris = np.mean(arr, axis=2, keepdims=True)
        arr = np.repeat(gris, 3, axis=2)
    elif modo == "rosa":
        arr[:, :, 0] *= 1.25
        arr[:, :, 1] *= 0.85

    result = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    suavizado = float(datos.get("suavizado", 0))
    return result.filter(ImageFilter.GaussianBlur((suavizado / 100.0) * 3.0)) if suavizado > 0 else result


def editar_rasgos(img, datos):
    color = str(datos.get("color", "#ff0055")).lstrip("#")
    if len(color) != 6:
        raise ValueError("Color hexadecimal inválido")
    rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    w, h = img.size
    x = max(0, min(w - 1, int(datos.get("coord_x", w // 2))))
    y = max(0, min(h - 1, int(datos.get("coord_y", h // 2))))
    zona = str(datos.get("zona", "Labios")).lower()
    factor = {"cabello": 0.18, "labio": 0.06, "sombra": 0.05, "rubor": 0.08}.get(
        next((k for k in ("cabello", "labio", "sombra", "rubor") if k in zona), "rubor"),
        0.08,
    )
    radio = max(1, int(w * factor))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((x - radio, y - radio, x + radio, y + radio), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(1, int(radio * 0.5))))
    overlay = Image.new("RGB", (w, h), rgb)
    alpha = max(0.0, min(1.0, float(datos.get("intensidad", 60)) / 100.0))
    mask = mask.point(lambda value: int(value * alpha))
    return Image.composite(overlay, img, mask)


def imagen_base64(img, calidad=88):
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=calidad)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{datetime.datetime.now().isoformat()}] {self.address_string()} {format % args}")

    def do_OPTIONS(self):
        respuesta(self, {}, 204)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/health"):
            respuesta(self, {"estatus": "ok", "motor": "NBO-A Genesis B"})
        elif url.path == "/pago-exito":
            payment_id = (query.get("payment_id") or query.get("collection_id") or [""])[0]
            referencia = (query.get("external_reference") or [""])[0]
            if not payment_id or not referencia:
                respuesta_html(self, pagina_html("Pago", "Faltan datos del pago."), 400)
                return
            try:
                res = procesar_pago(payment_id, referencia)
            except Exception as error:
                print(f"Error en pago-exito: {error}")
                respuesta_html(self, pagina_html("Pago", "No pudimos confirmar tu pago. Escríbenos con tu comprobante."), 500)
                return
            if res.get("licencia"):
                respuesta_html(self, pagina_html("¡Pago aprobado!", "Gracias por tu compra. Ingresa esta licencia en la app.", res["licencia"]))
            else:
                respuesta_html(self, pagina_html("Pago en proceso", "Tu pago aún no está aprobado. Recarga esta página en unos minutos."))
        elif url.path == "/pago-pendiente":
            respuesta_html(self, pagina_html("Pago pendiente", "Cuando se acredite tu pago recibirás tu licencia. Si ya pagaste, guarda tu comprobante."))
        elif url.path == "/pago-fallo":
            respuesta_html(self, pagina_html("Pago no completado", "No se realizó el cobro. Puedes intentarlo de nuevo."))
        else:
            respuesta(self, {"estatus": "error", "mensaje": "Ruta no encontrada"}, 404)

    def do_POST(self):
        try:
            url = urlparse(self.path)
            ruta = url.path
            query = parse_qs(url.query)
            length = int(self.headers.get("Content-Length", "0"))
            es_webhook = ruta == "/api/pagos/webhook"
            if length > 15 * 1024 * 1024 or (length <= 0 and not es_webhook):
                respuesta(self, {"estatus": "error", "mensaje": "Solicitud vacía o demasiado grande"}, 400)
                return

            raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            datos = json.loads(raw) if raw.strip() else {}
            if not isinstance(datos, dict):
                raise ValueError("JSON inválido")

            # Validación de licencia
            if ruta == "/api/validar_licencia":
                ok, mensaje, dias = validar_licencia_completa(
                    datos.get("licencia", ""),
                    datos.get("api_key"),
                    datos.get("token"),
                    datos.get("device_id"),
                    self.client_address[0],
                )
                respuesta(
                    self,
                    {"estatus": "ok" if ok else "error", "mensaje": mensaje, "dias_restantes": dias},
                    200 if ok else 403,
                )
                return

            # Crear preferencia de pago
            if ruta == "/api/pagos/crear_preferencia":
                email = datos.get("email", "")
                plan = datos.get("plan", "")
                pref = crear_preferencia(email=email, plan=plan)
                respuesta(self, {"estatus": "ok", **pref}, 200)
                return

            # Webhook Mercado Pago (formato webhooks con query o body, y formato legacy topic/id)
            if es_webhook:
                tipo = (query.get("type") or query.get("topic") or [None])[0] or datos.get("type") or datos.get("topic")
                data = datos.get("data") or {}
                payment_id = str((query.get("data.id") or query.get("id") or [None])[0] or data.get("id") or datos.get("id") or "")

                if tipo != "payment" or not payment_id:
                    respuesta(self, {"estatus": "ok", "mensaje": "Evento ignorado"}, 200)
                    return

                if not firma_webhook_valida(self.headers, payment_id):
                    respuesta(self, {"estatus": "error", "mensaje": "Firma inválida"}, 401)
                    return

                res = procesar_pago(payment_id)
                if not res.get("licencia"):
                    respuesta(self, {"estatus": "ok", "mensaje": f"Pago no aprobado ({res['status']})"}, 200)
                    return
                print(f"Pago {payment_id} aprobado, licencia generada")
                respuesta(self, {"estatus": "ok", "mensaje": "Pago aprobado y licencia generada", "payment_id": payment_id}, 200)
                return

            # Consulta estado de orden/pago (requiere payment_id y external_reference)
            if ruta == "/api/pagos/estado_orden":
                payment_id = str(datos.get("payment_id", "")).strip()
                referencia = str(datos.get("external_reference", "")).strip()
                if not payment_id or not referencia:
                    respuesta(self, {"estatus": "error", "mensaje": "Faltan payment_id y external_reference"}, 400)
                    return
                res = procesar_pago(payment_id, referencia)
                respuesta(self, {"estatus": "ok", **res}, 200)
                return

            # Endpoints de imagen protegidos por licencia
            if ruta in ("/api/procesar_rostro", "/api/editar_rasgos"):
                if not licencia_autorizada(self, datos):
                    return
                img = cargar_imagen(datos, "imagen_base64", "imagen", "imagen_procesada")
                result = procesar_rostro(img, datos) if ruta.endswith("rostro") else editar_rasgos(img, datos)
                respuesta(
                    self,
                    {
                        "estatus": "ok",
                        "imagen_procesada": imagen_base64(result),
                        "imagen_resultante": imagen_base64(result),
                    },
                )
                return

            respuesta(self, {"estatus": "error", "mensaje": "Endpoint no existe"}, 404)

        except (ValueError, json.JSONDecodeError, base64.binascii.Error) as error:
            respuesta(self, {"estatus": "error", "mensaje": str(error)}, 400)
        except Exception as error:
            print(f"Error interno: {error}")
            respuesta(self, {"estatus": "error", "mensaje": "Error interno del servidor"}, 500)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as server:
        server.allow_reuse_address = True
        print(f"Servidor NBO-A escuchando en puerto {PORT}")
        server.serve_forever()
