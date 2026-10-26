"""Servidor HTTP del backend NBO-A con validación de licencias y pagos MP."""
import base64
import datetime
import http.server
import io
import json
import os
import socketserver

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from db_manager import init_db
from validador_licencias import validar_licencia_completa, generar_licencia_real
from pagos_mp import crear_preferencia, obtener_pago, extraer_data_pago

PORT = int(os.environ.get("PORT", 8080))
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Evita duplicar licencias si llega más de una notificación del mismo pago
PAGOS_PROCESADOS = {}

init_db()


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
        if self.path in ("/", "/health"):
            respuesta(self, {"estatus": "ok", "motor": "NBO-A Genesis B"})
        else:
            respuesta(self, {"estatus": "error", "mensaje": "Ruta no encontrada"}, 404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 15 * 1024 * 1024:
                respuesta(self, {"estatus": "error", "mensaje": "Solicitud vacía o demasiado grande"}, 400)
                return

            datos = json.loads(self.rfile.read(length).decode("utf-8"))

            # Validación de licencia
            if self.path == "/api/validar_licencia":
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
            if self.path == "/api/pagos/crear_preferencia":
                email = datos.get("email", "")
                plan = datos.get("plan", "")
                pref = crear_preferencia(email=email, plan=plan)
                respuesta(self, {"estatus": "ok", **pref}, 200)
                return

            # Webhook Mercado Pago
            if self.path == "/api/pagos/webhook":
                tipo = datos.get("type") or datos.get("topic")
                data = datos.get("data") or {}
                payment_id = str(data.get("id") or datos.get("id") or "")

                if tipo != "payment" or not payment_id:
                    respuesta(self, {"estatus": "ok", "mensaje": "Evento ignorado"}, 200)
                    return

                # idempotencia básica
                if payment_id in PAGOS_PROCESADOS:
                    respuesta(self, {"estatus": "ok", "mensaje": "Pago ya procesado"}, 200)
                    return

                pago_json = obtener_pago(payment_id)
                pago = extraer_data_pago(pago_json)

                if pago["status"] != "approved":
                    respuesta(self, {"estatus": "ok", "mensaje": f"Pago no aprobado ({pago['status']})"}, 200)
                    return

                email = pago.get("email") or "cliente@salon.com"
                dias = int(pago.get("dias", 30))

                licencia = generar_licencia_real(dias=dias, email=email, device_id=None)
                if licencia.get("estatus") != "ok":
                    respuesta(self, {"estatus": "error", "mensaje": "No se pudo generar licencia"}, 500)
                    return

                PAGOS_PROCESADOS[payment_id] = {
                    "licencia": licencia["codigo"],
                    "email": email,
                    "plan": pago.get("plan"),
                    "dias": dias,
                    "fecha": datetime.datetime.now().isoformat(),
                }

                respuesta(
                    self,
                    {
                        "estatus": "ok",
                        "mensaje": "Pago aprobado y licencia generada",
                        "payment_id": payment_id,
                        "licencia": licencia["codigo"],
                        "email": email,
                        "dias": dias,
                    },
                    200,
                )
                return

            # Consulta estado de orden/pago
            if self.path == "/api/pagos/estado_orden":
                payment_id = str(datos.get("payment_id", "")).strip()
                if not payment_id:
                    respuesta(self, {"estatus": "error", "mensaje": "Falta payment_id"}, 400)
                    return

                if payment_id in PAGOS_PROCESADOS:
                    respuesta(self, {"estatus": "ok", "procesado": True, **PAGOS_PROCESADOS[payment_id]}, 200)
                    return

                pago_json = obtener_pago(payment_id)
                pago = extraer_data_pago(pago_json)
                respuesta(self, {"estatus": "ok", "procesado": False, "pago": pago}, 200)
                return

            # Endpoints de imagen protegidos por licencia
            if self.path in ("/api/procesar_rostro", "/api/editar_rasgos"):
                if not licencia_autorizada(self, datos):
                    return
                img = cargar_imagen(datos, "imagen_base64", "imagen", "imagen_procesada")
                result = procesar_rostro(img, datos) if self.path.endswith("rostro") else editar_rasgos(img, datos)
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
