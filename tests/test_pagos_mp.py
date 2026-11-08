import os
import unittest
from unittest.mock import patch

import pagos_mp


class PagosMPTests(unittest.TestCase):
    def test_configuracion_ofrece_licencia_semestral_a_804_mxn(self):
        import config

        self.assertEqual(config.DURACIONES["180"], 180)
        self.assertEqual(config.PRECIOS["180"], 804.0)
        self.assertNotIn("365", config.DURACIONES)

    def test_plan_semestral_cuesta_804_y_dura_180_dias(self):
        clave, plan = pagos_mp.obtener_plan("semestral")
        self.assertEqual(clave, "semestral")
        self.assertEqual(plan["precio"], 804.0)
        self.assertEqual(plan["dias"], 180)

    def test_no_crea_nuevas_preferencias_anuales(self):
        with self.assertRaisesRegex(ValueError, "semestral"):
            pagos_mp.obtener_plan("anual")

    def test_pagos_anuales_pendientes_conservan_su_duracion(self):
        pago = {
            "status": "approved",
            "id": 123,
            "payer": {"email": "cliente@example.com"},
            "metadata": {"plan": "anual"},
            "external_reference": "orden_anual_antigua",
        }
        resultado = pagos_mp.extraer_data_pago(pago)
        self.assertEqual(resultado["plan"], "anual")
        self.assertEqual(resultado["dias"], 365)

    @patch.dict(os.environ, {"MP_ACCESS_TOKEN": "test-token", "APP_BASE_URL": "https://example.test"})
    @patch("pagos_mp.mercadopago.SDK")
    def test_preferencia_semestral_envia_precio_y_duracion(self, sdk_factory):
        preferencia = sdk_factory.return_value.preference.return_value
        preferencia.create.return_value = {
            "response": {"id": "pref-1", "init_point": "https://pay.example.test"}
        }

        resultado = pagos_mp.crear_preferencia("cliente@example.com", "semestral")

        body = preferencia.create.call_args.args[0]
        self.assertEqual(body["items"][0]["unit_price"], 804.0)
        self.assertEqual(body["items"][0]["currency_id"], "MXN")
        self.assertEqual(body["metadata"]["dias_licencia"], 180)
        self.assertEqual(resultado["dias"], 180)
        self.assertTrue(resultado["external_reference"].startswith("orden_semestral_"))


if __name__ == "__main__":
    unittest.main()
