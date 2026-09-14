from django import forms
from django.contrib.auth.models import Group, User

INPUT_CLASS = (
    "w-full px-4 py-2 border rounded-lg focus:ring-2 "
    "focus:ring-indigo-500 focus:outline-none border-gray-300"
)


class UsuarioForm(forms.ModelForm):
    senha = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
        help_text="Obrigatória na criação. Deixe em branco para manter a senha atual.",
    )
    senha_confirmacao = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
        label="Confirmar senha",
    )
    grupos = forms.ModelMultipleChoiceField(
        queryset=Group.objects.order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        self.editor = kwargs.pop("editor", None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["grupos"].initial = self.instance.groups.all()
        else:
            self.fields["senha"].required = True
            self.fields["senha_confirmacao"].required = True
        if self._bloqueia_grupos():
            self.fields["grupos"].disabled = True

    def _bloqueia_grupos(self):
        if not self.instance.pk or self.editor is None:
            return False
        if self.editor.is_superuser:
            return False
        return self.instance.pk == self.editor.pk

    def clean(self):
        cleaned = super().clean()
        senha = cleaned.get("senha") or ""
        confirmacao = cleaned.get("senha_confirmacao") or ""
        if senha or confirmacao:
            if senha != confirmacao:
                self.add_error("senha_confirmacao", "As senhas não coincidem.")
        if not self.instance.pk and not senha:
            self.add_error("senha", "Informe uma senha para o novo usuário.")
        return cleaned

    def save(self, commit=True):
        usuario = super().save(commit=False)
        senha = self.cleaned_data.get("senha") or ""
        if senha:
            usuario.set_password(senha)
        elif not usuario.pk:
            raise ValueError("Senha obrigatória na criação.")
        if commit:
            usuario.save()
            if not self._bloqueia_grupos():
                usuario.groups.set(self.cleaned_data.get("grupos") or [])
        return usuario
