document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("[data-origens-url]");
    const cliente = document.getElementById("id_cobranca_cliente");
    const orcamento = document.getElementById("id_cobranca_orcamento");
    const ordem = document.getElementById("id_cobranca_os");
    const original = document.getElementById("id_valor_original");
    const desconto = document.getElementById("id_desconto");
    const acrescimo = document.getElementById("id_acrescimo");
    const preview = document.getElementById("valor-final-preview");

    function numero(campo) {
        if (!campo || !campo.value) {
            return 0;
        }
        const valor = Number(campo.value.replace(",", "."));
        return Number.isFinite(valor) ? valor : 0;
    }

    function atualizarPreview() {
        if (!preview) {
            return;
        }
        const final = numero(original) - numero(desconto) + numero(acrescimo);
        preview.textContent = "R$ " + final.toFixed(2).replace(".", ",");
    }

    function preencherSelect(select, itens, rotuloVazio) {
        if (!select) {
            return;
        }
        const atual = select.value;
        select.innerHTML = "";
        const vazio = document.createElement("option");
        vazio.value = "";
        vazio.textContent = rotuloVazio;
        select.appendChild(vazio);
        itens.forEach(function (item) {
            const option = document.createElement("option");
            option.value = String(item.id);
            option.textContent = item.label;
            select.appendChild(option);
        });
        if (atual) {
            select.value = atual;
        }
    }

    function carregarOrigens() {
        if (!form || !cliente || !cliente.value) {
            return;
        }
        const url = form.getAttribute("data-origens-url").replace("/0/", "/" + cliente.value + "/");
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (resposta) {
                return resposta.json();
            })
            .then(function (dados) {
                preencherSelect(orcamento, dados.orcamentos || [], "---------");
                preencherSelect(ordem, dados.ordens || [], "---------");
            })
            .catch(function () {});
    }

    if (original) {
        [original, desconto, acrescimo].forEach(function (campo) {
            if (campo) {
                campo.addEventListener("input", atualizarPreview);
            }
        });
        atualizarPreview();
    }

    if (cliente) {
        cliente.addEventListener("change", carregarOrigens);
    }
});
