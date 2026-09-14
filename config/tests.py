from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.finders import find
from django.test import SimpleTestCase

from config.settings import build_databases


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


class DatabaseConfigTests(SimpleTestCase):
    def test_sem_database_url_usa_sqlite(self):
        base = Path("/tmp/valvulman")
        bancos = build_databases(database_url=None, debug=True, base_dir=base)
        self.assertEqual(bancos["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(bancos["default"]["NAME"], base / "db.sqlite3")

    def test_database_url_vazia_usa_sqlite(self):
        bancos = build_databases(
            database_url="   ",
            debug=True,
            base_dir=Path("/tmp/valvulman"),
        )
        self.assertEqual(bancos["default"]["ENGINE"], "django.db.backends.sqlite3")

    def test_com_database_url_usa_postgresql(self):
        bancos = build_databases(
            database_url="postgres://usuario:senha@localhost:5432/valvulman",
            debug=False,
            base_dir=Path("/tmp/valvulman"),
        )
        engine = bancos["default"]["ENGINE"]
        self.assertTrue(
            engine.startswith("django.db.backends.postgresql"),
            engine,
        )
        self.assertEqual(bancos["default"]["NAME"], "valvulman")
        self.assertEqual(bancos["default"].get("OPTIONS", {}).get("sslmode"), "require")

    def test_database_url_em_debug_nao_exige_ssl(self):
        bancos = build_databases(
            database_url="postgres://usuario:senha@localhost:5432/valvulman",
            debug=True,
            base_dir=Path("/tmp/valvulman"),
        )
        self.assertNotEqual(
            bancos["default"].get("OPTIONS", {}).get("sslmode"),
            "require",
        )
