from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from clientes.models import Cliente


@login_required
def relatorio_tecnico(request):
    clientes = Cliente.objects.all().order_by("nome")

    return render(
        request,
        "relatorio_tecnico.html",
        {
            "clientes": clientes,
        },
    )
