document.addEventListener('DOMContentLoaded', function () {
    // Seleciona os campos pelo ID padrão gerado pelo Django
    const inputCnpj = document.getElementById('id_cnpj');
    const inputCep = document.getElementById('id_cep');
    const inputEndereco = document.getElementById('id_endereco');

    // MÁSCARAS DE ENTRADA
    function mascararCNPJ(valor) {
        return valor
            .replace(/\D/g, '')
            .slice(0, 14)
            .replace(/^(\d{2})(\d)/, '$1.$2')
            .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
            .replace(/\.(\d{3})(\d)/, '.$1/$2')
            .replace(/(\d{4})(\d)/, '$1-$2');
    }

    function mascararCEP(valor) {
        return valor
            .replace(/\D/g, '')
            .slice(0, 8)
            .replace(/^(\d{5})(\d)/, '$1-$2');
    }

    if (inputCnpj) {
        inputCnpj.setAttribute('maxlength', '18');
        inputCnpj.addEventListener('input', function (e) {
            e.target.value = mascararCNPJ(e.target.value);
        });
    }

    if (inputCep) {
        inputCep.setAttribute('maxlength', '9');
        inputCep.addEventListener('input', function (e) {
            e.target.value = mascararCEP(e.target.value);
            
            // Busca o endereço se o CEP possuir os 8 dígitos numéricos completos
            const cepLimpo = e.target.value.replace(/\D/g, '');
            if (cepLimpo.length === 8) {
                buscarEnderecoPorCEP(cepLimpo);
            }
        });
    }

    // BUSCA AUTOMÁTICA DE ENDEREÇO (ViaCEP)
    async function buscarEnderecoPorCEP(cep) {
        if (!inputEndereco) return;

        try {
            inputEndereco.value = "Buscando endereço...";
            inputEndereco.disabled = true;

            const response = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
            const data = await response.json();

            if (data.erro) {
                inputEndereco.value = "";
                alert("CEP não encontrado.");
            } else {
                inputEndereco.value = `${data.logradouro}, - ${data.bairro}, ${data.localidade}/${data.uf}`;
            }
        } catch (error) {
            console.error("Erro ao consultar CEP:", error);
            inputEndereco.value = "";
        } finally {
            inputEndereco.disabled = false;
        }
    }
});