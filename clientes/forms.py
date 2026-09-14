from django import forms

from .cnpj import only_digits, validate_cnpj
from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cnpj", "cep", "endereco", "contato_principal", "telefone", "email"]
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "Razão Social ou Nome Completo",
                }
            ),
            "cnpj": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "00.000.000/0001-00",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                }
            ),
            "cep": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "00000-000",
                }
            ),
            "endereco": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "Rua, número, bairro, cidade/UF",
                }
            ),
            "contato_principal": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "Nome de quem solicita o serviço",
                }
            ),
            "telefone": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "(14) 99999-9999",
                    "autocomplete": "tel",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none border-gray-300",
                    "placeholder": "contato@empresa.com",
                    "autocomplete": "email",
                }
            ),
        }

    def clean_cnpj(self):
        formatted = validate_cnpj(self.cleaned_data.get("cnpj", ""))
        digits = only_digits(formatted)
        existentes = Cliente.objects.exclude(pk=self.instance.pk)
        for cliente in existentes.only("cnpj"):
            if only_digits(cliente.cnpj) == digits:
                raise forms.ValidationError("Já existe um cliente com este CNPJ.")
        return formatted
