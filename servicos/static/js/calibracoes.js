document.addEventListener("DOMContentLoaded", function () {
    const tbody = document.getElementById("pontos-tbody");
    const template = document.getElementById("ponto-empty-form");
    const totalInput = document.getElementById("id_pontos-TOTAL_FORMS");
    const btnAdd = document.getElementById("btn-add-ponto");
    const btnRemove = document.getElementById("btn-remove-ponto");

    if (!tbody || !template || !totalInput || !btnAdd) {
        return;
    }

    function linhas() {
        return Array.from(tbody.querySelectorAll("tr.ponto-form"));
    }

    function linhasVisiveis() {
        return linhas().filter(function (linha) {
            return linha.style.display !== "none";
        });
    }

    function atualizarTotal() {
        totalInput.value = String(linhas().length);
    }

    function maiorOrdemVisivel() {
        let maior = 0;
        linhasVisiveis().forEach(function (linha) {
            const campo = linha.querySelector('input[name$="-ordem"]');
            const valor = campo ? parseInt(campo.value, 10) : 0;
            if (!isNaN(valor) && valor > maior) {
                maior = valor;
            }
        });
        return maior;
    }

    function substituirPrefixo(raiz, indice) {
        raiz.querySelectorAll("[name], [id], [for]").forEach(function (elemento) {
            ["name", "id", "for"].forEach(function (atributo) {
                const valor = elemento.getAttribute(atributo);
                if (valor && valor.indexOf("__prefix__") !== -1) {
                    elemento.setAttribute(
                        atributo,
                        valor.replace(/__prefix__/g, String(indice))
                    );
                }
            });
        });
    }

    function adicionarPonto() {
        const indice = linhas().length;
        const fragmento = template.content.cloneNode(true);
        substituirPrefixo(fragmento, indice);
        const linha = fragmento.querySelector("tr.ponto-form") || fragmento.querySelector("tr");
        if (!linha) {
            return;
        }
        const proxima = maiorOrdemVisivel() + 1;
        tbody.appendChild(linha);
        const ordem = linha.querySelector('input[name$="-ordem"]');
        if (ordem) {
            ordem.value = String(proxima);
        }
        atualizarTotal();
    }

    function removerUltimoPonto() {
        const visiveis = linhasVisiveis();
        if (visiveis.length <= 1) {
            return;
        }
        const ultima = visiveis[visiveis.length - 1];
        const idCampo = ultima.querySelector('input[name$="-id"]');
        const deleteCampo = ultima.querySelector('input[name$="-DELETE"]');
        if (idCampo && idCampo.value && deleteCampo) {
            deleteCampo.checked = true;
            ultima.style.display = "none";
        } else {
            ultima.remove();
        }
        atualizarTotal();
    }

    btnAdd.addEventListener("click", function (event) {
        event.preventDefault();
        adicionarPonto();
    });

    if (btnRemove) {
        btnRemove.addEventListener("click", function (event) {
            event.preventDefault();
            removerUltimoPonto();
        });
    }
});
