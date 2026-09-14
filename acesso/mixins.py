from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied


class PermissaoRequeridaMixin(PermissionRequiredMixin):
    """Anônimo é redirecionado ao login; autenticado sem permissão recebe 403."""

    raise_exception = False

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(self.get_permission_denied_message())
        return super().handle_no_permission()
