import http.server
import socketserver
import json
import os
import base64
import io
import datetime
import hashlib
import numpy as np
from PIL import Image, ImageFilter

# --- SISTEMA DE LICENCIAMIENTO NATIVO ---
SECRET_SEED = "GENESIS_B_SECRET_2026"

def validar_licencia_servidor(clave_licencia):
    """Valida si una clave de licencia sigue vigente en el tiempo."""
    try:
        partes = clave_licencia.split('-')
        if len(partes) < 4:
            return False, "Estructura de licencia inválida"
        
        fecha_exp_str = f"{partes[1]}-{partes[2]}-{partes[3]}"
        fecha_exp = datetime.datetime.strptime(fecha_exp_str, "%Y-%m-%d").date()
        
        hoy = datetime.date.today()
        if hoy <= fecha_exp:
            dias_restantes = (fecha_exp - hoy).days
            return True, f"Licencia Válida. Quedan {dias_restantes} días."
        else:
            return False, "La licencia ha expirado."
    except Exception as e:
        return False, "Clave de licencia no reconocida."

# --- MOTOR NBO-A GÉNESIS B ---
def relu_mod_211(S):
    if S <= 0:
        return 0.0
    y1 = S * 0.5
    return y1 * (211.0 / (211.0 + y1))

def procesar_matriz_rostro(img_pil, modo_color, brillo, contraste, suavizado):
    if modo_color == 'gris':
        img_pil = img_pil.convert('L').convert('RGB')
    
    arr = np.array(img_pil, dtype=np.float32)

    factor_brillo = relu_mod_211(brillo) / 50.0
    factor_contraste = relu_mod_211(contraste) / 50.0

    arr = (arr - 128.0) * factor_contraste + 128.0 + (factor_brillo * 25.5)

    if modo_color == 'rosa':
        arr[:, :, 0] *= 1.35  # Canal Rojo realzado
        arr[:, :, 1] *= 0.80  # Canal Verde reducido
        arr[:, :, 2] *= 1.20  # Canal Azul moderado (efecto magenta/rosa)

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img_resultado = Image.fromarray(arr)

    if suavizado > 0:
        radio_blur = (suavizado / 100.0) * 3.0
        img_resultado = img_resultado.filter(ImageFilter.GaussianBlur(radius=radio_blur))

    return img_resultado

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

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            datos = json.loads(post_data.decode('utf-8'))

            # Endpoint de validación de licencia
            if self.path == '/api/validar_licencia':
                 licencia = datos.get('licencia', '')
                 validez, mensaje = validar_licencia_servidor(licencia)
                 self._set_headers()
                 self.wfile.write(json.dumps({"estatus": "ok" if validez else "error", "mensaje": mensaje}).encode('utf-8'))
                 return

            # Endpoint de procesamiento de rostro con IA
            if self.path == '/api/procesar_rostro':
                # Validar licencia antes de permitir procesar la imagen
                licencia = datos.get('licencia', '')
                validez, mensaje = validar_licencia_servidor(licencia)
                if not validez:
                    self._set_headers(403)
                    self.wfile.write(json.dumps({"estatus": "error", "mensaje": f"Acceso denegado: {mensaje}"}).encode('utf-8'))
                    return

                img_b64 = datos.get('imagen').split(',')[1]
                img_bytes = base64.b64decode(img_b64)
                img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

                modo_color = datos.get('modo_color', 'normal')
                brillo = float(datos.get('brillo', 50))
                contraste = float(datos.get('contraste', 50))
                suavizado = float(datos.get('suavizado', 0))

                img_editada = procesar_matriz_rostro(img, modo_color, brillo, contraste, suavizado)

                buffered = io.BytesIO()
                img_editada.save(buffered, format="JPEG", quality=85)
                img_resultado_b64 = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode('utf-8')

                self._set_headers()
                self.wfile.write(json.dumps({"estatus": "ok", "imagen_procesada": img_resultado_b64}).encode('utf-8'))
                return

            self.send_error(404)
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

PORT = int(os.environ.get("PORT", 8080))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"--- Servidor NBO-A Génesis B en Puerto {PORT} ---")
with socketserver.TCPServer(("", PORT), HandlerProcesador) as httpd:
    httpd.serve_forever()
