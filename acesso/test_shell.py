from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from acesso.permissoes import GRUPO_ADMINISTRADOR, GRUPO_CONSULTA, GRUPO_TECNICO
from acesso.shell import cargo_shell


class CargoShellTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_permissoes")

    def test_prioriza_administrador_entre_varios_grupos(self):
        user = User.objects.create_user("multi", password="x")
        user.groups.add(
            Group.objects.get(name=GRUPO_TECNICO),
            Group.objects.get(name=GRUPO_ADMINISTRADOR),
        )
        self.assertEqual(cargo_shell(user), "Administrador")

    def test_tecnico(self):
        user = User.objects.create_user("tec", password="x")
        user.groups.add(Group.objects.get(name=GRUPO_TECNICO))
        self.assertEqual(cargo_shell(user), "Técnico")

    def test_superuser_sem_grupo(self):
        user = User.objects.create_superuser("root", "root@local", "x")
        self.assertEqual(cargo_shell(user), "Administrador")

    def test_anonimo(self):
        class Anon:
            is_authenticated = False

        self.assertEqual(cargo_shell(Anon()), "")

    def test_home_exibe_grupo_e_nao_duplica_h1_na_topbar(self):
        user = User.objects.create_user("consulta-shell", password="x")
        user.groups.add(Group.objects.get(name=GRUPO_CONSULTA))
        self.client.force_login(user)
        resposta = self.client.get(reverse("home"))
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertNotIn(">Metrologia<", html)
        inicio = html.find('class="vm-topbar"')
        fim = html.find("</header>", inicio)
        topbar = html[inicio:fim]
        self.assertNotIn("<h1", topbar)
        self.assertIn("Consulta", topbar)
        self.assertIn("Principal", topbar)
        self.assertIn('class="vm-breadcrumb"', topbar)
        self.assertIn('aria-controls="sidebar"', html)
