from acesso.shell import cargo_shell


def shell(request):
    return {"shell_cargo": cargo_shell(getattr(request, "user", None))}
