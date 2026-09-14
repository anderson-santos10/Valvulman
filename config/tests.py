from django.conf import settings
from django.contrib.staticfiles.finders import find
from django.test import SimpleTestCase


class StaticFilesFinderTests(SimpleTestCase):
    def test_arquivos_oficiais_existem_nos_finders(self):
        esperados = [
            "css/design-system.css",
            "css/layout.css",
            "css/components/buttons.css",
            "css/login.css",
            "js/design-system.js",
            "js/login.js",
        ]
        for caminho in esperados:
            with self.subTest(caminho=caminho):
                encontrado = find(caminho)
                self.assertIsNotNone(
                    encontrado,
                    "Staticfiles finder não localizou {0}".format(caminho),
                )

    def test_whitenoise_vem_depois_do_security_middleware(self):
        middleware = list(settings.MIDDLEWARE)
        security = "django.middleware.security.SecurityMiddleware"
        whitenoise = "whitenoise.middleware.WhiteNoiseMiddleware"
        self.assertIn(security, middleware)
        self.assertIn(whitenoise, middleware)
        self.assertEqual(middleware.index(whitenoise), middleware.index(security) + 1)

    def test_storage_estatico_usa_whitenoise(self):
        backend = settings.STORAGES["staticfiles"]["BACKEND"]
        self.assertEqual(backend, "whitenoise.storage.CompressedStaticFilesStorage")

    def test_whitenoise_serve_css_oficial(self):
        resposta = self.client.get("/static/css/design-system.css")
        self.assertEqual(resposta.status_code, 200)
        corpo = b"".join(resposta.streaming_content)
        self.assertIn(b"--vm-color-primary", corpo)
