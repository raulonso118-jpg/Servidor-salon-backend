import http.server
import socketserver
import json
import os
import base64
import io
import datetime
import hashlib
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

# --- SISTEMA DE LICENCIAMIENTO NATIVO ---
SECRET_SEED = "GENESIS_B_SECRET_2026"

def validar_licencia_servidor(clave_licencia):
    """Valida si una clave de licencia sigue vigente en el tiempo."""
    try:
        if not clave_licencia:
            return False, "Licencia vacía"
        partes = clave_licencia.split('-')
        if len(partes) < 4:
            return False, "Estructura de licencia inválida"

        # Formato esperado: GENESIS-YYYY-MM-DD-XXXX o XXXX-YYYY-MM-DD
        # Intentamos buscar fecha YYYY-MM-DD en la clave
        fecha_exp = None
        for i in range(len(partes)-2):
            try:
                fecha_str = f"{partes[i]}-{partes[i+1]}-{partes[i+2]}"
                fecha_exp = datetime.datetime.strptime(fecha_str, "%Y-%m-%d").date()
                break
            except:
                continue

        if not fecha_exp:
            # Si no hay fecha, si contiene TEST la dejamos pasar en desarrollo
            if "TEST" in clave_licencia:
                return True, "Licencia de prueba válida"
            return False, "Clave de licencia no reconocida"

        hoy = datetime.date.today()
        if hoy <= fecha_exp:
            dias_restantes = (fecha_exp - hoy).days
            return True, f"Licencia Válida. Quedan {dias_restantes} días."
        else:
            return False, "La licencia ha expirado."
    except Exception as e:
        return False, f"Clave no reconocida: {str(e)}"

# --- MOTOR NBO-A GÉNESIS B ---
def relu_mod_211(S):
    if S <= 0:
        return 0.0
    y1 = S * 0.5
    return y1 * (211.0 / (211.0 + y1))

def procesar_matriz_rostro(img_pil, modo_color, brillo, contraste, suavizado, tono_r=100, tono_b=100):
    if modo_color == 'gris':
        img_pil = img_pil.convert('L').convert('RGB')

    arr = np.array(img_pil, dtype=np.float32)

    # Brillo y Contraste con tu función relu
    factor_brillo = relu_mod_211(brillo) / 50.0
    factor_contraste = relu_mod_211(contraste) / 50.0

    arr = (arr - 128.0) * factor_contraste + 128.0 + (factor_brillo * 25.5)

    # Tonos R y B
    factor_r = tono_r / 100.0
    factor_b = tono_b / 100.0
    arr[:, :, 0] *= factor_r
    arr[:, :, 2] *= factor_b

    if modo_color == 'rosa':
        arr[:, :, 0] *= 1.35
        arr[:, :, 1] *= 0.80
        arr[:, :, 2] *= 1.20

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img_resultado = Image.fromarray(arr)

    if suavizado > 0:
        radio_blur = (suavizado / 100.0) * 3.0
        if radio_blur > 0:
            img_resultado = img_resultado.filter(ImageFilter.GaussianBlur(radius=radio_blur))

    return img_resultado

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def procesar_edicion_zona(img_pil, zona, coord_x, coord_y, color_hex, intensidad):
    """
    Edita una zona específica donde hizo doble toque el usuario.
    zona: Cabello, Labios, Sombras, Rubor
    """
    img_pil = img_pil.convert('RGBA')
    w, h = img_pil.size

    # Asegurar coordenadas dentro de la imagen
    coord_x = max(0, min(w-1, int(coord_x)))
    coord_y = max(0, min(h-1, int(coord_y)))

    # Intensidad 10-100 -> 0.1 a 0.9
    alpha_factor = float(intensidad) / 100.0
    if alpha_factor <= 0:
        alpha_factor = 0.6

    color_rgb = hex_to_rgb(color_hex)

    # Definir radio según zona
    zona = zona.lower()
    if 'cabello' in zona:
        radio_base = int(w * 0.18) # 18% del ancho para cabello
        feather = radio_base * 0.4
    elif 'labio' in zona:
        radio_base = int(w * 0.06)
        feather = radio_base * 0.5
    elif 'sombra' in zona:
        radio_base = int(w * 0.05)
        feather = radio_base * 0.6
    elif 'rubor' in zona:
        radio_base = int(w * 0.08)
        feather = radio_base * 0.7
    else:
        radio_base = int(w * 0.1)
        feather = radio_base * 0.5

    # Crear capa de color con máscara circular suave
    overlay = Image.new('RGBA', (w, h), (0,0,0,0))
    mask = Image.new('L', (w, h), 0)
    draw_mask = ImageDraw.Draw(mask)

    # Dibujar círculo sólido
    draw_mask.ellipse(
        (coord_x - radio_base, coord_y - radio_base,
         coord_x + radio_base, coord_y + radio_base),
        fill=255
    )

    # Suavizar bordes de la máscara para que no se vea recorte duro
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))

    # Crear capa de color
    color_layer = Image.new('RGBA', (w, h), color_rgb + (int(255 * alpha_factor),))

    # Aplicar máscara a la capa de color
    overlay = Image.composite(color_layer, Image.new('RGBA', (w,h), (0,0,0,0)), mask)

    # Mezcla según zona
    if 'cabello' in zona:
        # Para cabello usamos mezcla color + overlay
        base = img_pil.copy()
        # Mezclar solo donde hay máscara
        result = Image.alpha_composite(base, overlay)
        # Si quieres efecto tinte más realista, baja un poco el brillo del cabello
        return result.convert('RGB')
    elif 'labio' in zona:
        # Labios más intenso y saturado
        result = Image.alpha_composite(img_pil, overlay)
        return result.convert('RGB')
    else:
        # Sombras y rubor con mezcla suave
        result = Image.alpha_composite(img_pil, overlay)
        return result.convert('RGB')

class HandlerProcesador(http.server.SimpleHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        # Health check para Render
        if self.path == '/' or self.path == '/health':
            self._set_headers()
            self.wfile.write(json.dumps({"estatus": "ok", "motor": "NBO-A Genesis B", "endpoints": ["/api/validar_licencia","/api/procesar_rostro","/api/editar_rasgos"]}).encode('utf-8'))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"estatus": "error", "mensaje": "Ruta no encontrada. Usa POST"}).encode('utf-8'))

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._set_headers(400)
                self.wfile.write(json.dumps({"estatus": "error", "mensaje": "Body vacío"}).encode('utf-8'))
                return

            post_data = self.rfile.read(content_length)
            datos = json.loads(post_data.decode('utf-8'))

            # Endpoint de validación de licencia
            if self.path == '/api/validar_licencia':
                 licencia = datos.get('licencia', '')
                 validez, mensaje = validar_licencia_servidor(licencia)
                 self._set_headers()
                 self.wfile.write(json.dumps({"estatus": "ok" if validez else "error", "mensaje": mensaje}).encode('utf-8'))
                 return

            # Endpoint de procesamiento de rostro con IA (Global)
            if self.path == '/api/procesar_rostro':
                # Validar licencia - opcional en modo TEST
                licencia = datos.get('licencia', '')
                if licencia and "TEST" not in licencia:
                    validez, mensaje = validar_licencia_servidor(licencia)
                    if not validez:
                        self._set_headers(403)
                        self.wfile.write(json.dumps({"estatus": "error", "mensaje": f"Acceso denegado: {mensaje}"}).encode('utf-8'))
                        return

                # Soporta ambos nombres: imagen y imagen_base64
                img_b64_raw = datos.get('imagen') or datos.get('imagen_base64') or datos.get('imagen_procesada')
                if not img_b64_raw:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"estatus": "error", "mensaje": "No se envió imagen"}).encode('utf-8'))
                    return

                if ',' in img_b64_raw:
                    img_b64 = img_b64_raw.split(',')[1]
                else:
                    img_b64 = img_b64_raw

                img_bytes = base64.b64decode(img_b64)
                img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

                modo_color = datos.get('modo_color', 'normal')
                brillo = float(datos.get('brillo', 100))
                contraste = float(datos.get('contraste', 100))
                suavizado = float(datos.get('suavizado', 0))
                tono_r = float(datos.get('tono_r', datos.get('tono_rojo', 100)))
                tono_b = float(datos.get('tono_b', datos.get('tono_azul', 100)))

                img_editada = procesar_matriz_rostro(img, modo_color, brillo, contraste, suavizado, tono_r, tono_b)

                buffered = io.BytesIO()
                img_editada.save(buffered, format="JPEG", quality=85)
                img_resultado_b64 = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode('utf-8')

                self._set_headers()
                self.wfile.write(json.dumps({"estatus": "ok", "imagen_procesada": img_resultado_b64, "imagen_resultante": img_resultado_b64}).encode('utf-8'))
                return

            # NUEVO Endpoint de edición de rasgos por doble toque
            if self.path == '/api/editar_rasgos':
                # No bloqueamos por licencia si es TEST para que puedas probar
                licencia = datos.get('licencia', '')
                if licencia and "TEST" not in licencia:
                    validez, mensaje = validar_licencia_servidor(licencia)
                    if not validez:
                        self._set_headers(403)
                        self.wfile.write(json.dumps({"estatus": "error", "mensaje": f"Acceso denegado: {mensaje}"}).encode('utf-8'))
                        return

                img_b64_raw = datos.get('imagen_base64') or datos.get('imagen') or datos.get('imagen_base')
                if not img_b64_raw:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"estatus": "error", "mensaje": "No se envió imagen_base64"}).encode('utf-8'))
                    return

                if ',' in img_b64_raw:
                    img_b64 = img_b64_raw.split(',')[1]
                else:
                    img_b64 = img_b64_raw

                img_bytes = base64.b64decode(img_b64)
                img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

                zona = datos.get('zona', 'Cabello')
                coord_x = int(datos.get('coord_x', datos.get('x', img.width//2)))
                coord_y = int(datos.get('coord_y', datos.get('y', img.height//2)))
                color = datos.get('color', '#ff0000')
                intensidad = datos.get('intensidad', 60)

                # Ajustar coordenadas si vienen escaladas (ej. canvas 500 pero imagen original 1000)
                # El frontend ya manda coordenadas corregidas, pero por si acaso
                # No re-escalamos aquí

                img_editada = procesar_edicion_zona(img, zona, coord_x, coord_y, color, intensidad)

                buffered = io.BytesIO()
                img_editada.save(buffered, format="JPEG", quality=90)
                img_resultado_b64 = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode('utf-8')

                self._set_headers()
                self.wfile.write(json.dumps({"estatus": "ok", "imagen_resultante": img_resultado_b64, "imagen_procesada": img_resultado_b64, "zona": zona}).encode('utf-8'))
                return

            self._set_headers(404)
            self.wfile.write(json.dumps({"estatus": "error", "mensaje": f"Endpoint {self.path} no existe"}).encode('utf-8'))

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_headers(500)
            self.wfile.write(json.dumps({"estatus": "error", "mensaje": str(e)}).encode('utf-8'))

PORT = int(os.environ.get("PORT", 8080))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"--- Servidor NBO-A Génesis B en Puerto {PORT} ---")
print(f"Endpoints: /api/validar_licencia, /api/procesar_rostro, /api/editar_rasgos")
with socketserver.TCPServer(("", PORT), HandlerProcesador) as httpd:
    httpd.allow_reuse_address = True
    httpd.serve_forever()
