document.addEventListener("DOMContentLoaded", function () {
    const botaoImprimir = document.getElementById("btn-imprimir-os");
    if (botaoImprimir) {
        botaoImprimir.addEventListener("click", function (event) {
            event.preventDefault();
            window.print();
        });
    }

    const tbody = document.getElementById("itens-os-tbody");
    const template = document.getElementById("item-os-empty-form");
    const totalInput = document.querySelector('[name="itens-TOTAL_FORMS"]');
    const btnAdd = document.getElementById("btn-add-item-os");
    const btnRemove = document.getElementById("btn-remove-item-os");
    const clienteCampo = document.getElementById("id_os_cliente") || document.getElementById("id_cliente");
    const formOs = document.querySelector("[data-instrumentos-url]");

    function linhas() {
        return tbody ? Array.from(tbody.querySelectorAll("tr.item-os-form")) : [];
    }

    function visiveis() {
        return linhas().filter(function (linha) {
            return linha.style.display !== "none";
        });
    }

    function atualizarTotal() {
        if (totalInput) {
            totalInput.value = String(linhas().length);
        }
    }

    function aplicarTipo(linha) {
        const tipoCampo = linha.querySelector('select[name$="-tipo_equipamento"]');
        const tipo = tipoCampo ? tipoCampo.value : "instrumento";
        linha.querySelectorAll(".item-os-equipamento").forEach(function (bloco) {
            const campo = bloco.getAttribute("data-campo");
            bloco.style.display = campo === tipo ? "" : "none";
            if (campo !== tipo) {
                const select = bloco.querySelector("select");
                if (select && !select.disabled) {
                    select.value = "";
                }
            }
        });
    }

    function ligarTipo(linha) {
        const tipoCampo = linha.querySelector('select[name$="-tipo_equipamento"]');
        if (!tipoCampo || tipoCampo.dataset.ligado) {
            return;
        }
        tipoCampo.dataset.ligado = "1";
        tipoCampo.addEventListener("change", function () {
            aplicarTipo(linha);
        });
        aplicarTipo(linha);
    }

    function preencherSelect(select, opcoes) {
        if (!select || select.disabled) {
            return;
        }
        const atual = select.value;
        select.innerHTML = '<option value="">---------</option>';
        opcoes.forEach(function (item) {
            const option = document.createElement("option");
            option.value = String(item.id);
            option.textContent = item.label;
            if (String(item.id) === atual) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    }

    function carregarEquipamentos() {
        if (!clienteCampo || !formOs || !tbody) {
            return;
        }
        const clienteId = clienteCampo.value;
        if (!clienteId) {
            return;
        }
        const url = formOs.getAttribute("data-instrumentos-url").replace("/0/", "/" + clienteId + "/");
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (resposta) {
                return resposta.json();
            })
            .then(function (dados) {
                const instrumentos = dados.instrumentos || [];
                const valvulas = dados.valvulas || [];
                linhas().forEach(function (linha) {
                    preencherSelect(linha.querySelector('select[name$="-instrumento"]'), instrumentos);
                    preencherSelect(linha.querySelector('select[name$="-valvula"]'), valvulas);
                    ligarTipo(linha);
                });
                if (formOs.getAttribute("data-preencher-contato") === "1" && dados.cliente) {
                    const contato = dados.cliente;
                    const solicitante = document.getElementById("id_solicitante");
                    const telefone = document.getElementById("id_telefone_solicitante");
                    const email = document.getElementById("id_email_solicitante");
                    const extra = document.querySelector('[name="contato_solicitante"]');
                    if (solicitante) {
                        solicitante.value = contato.contato_principal || "";
                    }
                    if (telefone) {
                        telefone.value = contato.telefone || "";
                    }
                    if (email) {
                        email.value = contato.email || "";
                    }
                    if (extra) {
                        extra.value = contato.telefone || contato.email || "";
                    }
                }
            })
            .catch(function () {
                return;
            });
    }

    if (tbody && template && totalInput && btnAdd) {
        linhas().forEach(ligarTipo);

        btnAdd.addEventListener("click", function (event) {
            event.preventDefault();
            const indice = linhas().length;
            const html = template.innerHTML.replace(/__prefix__/g, String(indice));
            const wrapper = document.createElement("tbody");
            wrapper.innerHTML = html.trim();
            const linha = wrapper.querySelector("tr");
            if (!linha) {
                return;
            }
            tbody.appendChild(linha);
            atualizarTotal();
            ligarTipo(linha);
            carregarEquipamentos();
        });

        if (btnRemove) {
            btnRemove.addEventListener("click", function (event) {
                event.preventDefault();
                const lista = visiveis();
                if (lista.length <= 1) {
                    return;
                }
                const ultima = lista[lista.length - 1];
                const idCampo = ultima.querySelector('input[name$="-id"]');
                const deleteCampo = ultima.querySelector('input[name$="-DELETE"]');
                if (idCampo && idCampo.value && deleteCampo) {
                    deleteCampo.checked = true;
                    ultima.style.display = "none";
                } else {
                    ultima.remove();
                }
                atualizarTotal();
            });
        }
    }

    if (clienteCampo) {
        clienteCampo.addEventListener("change", carregarEquipamentos);
        carregarEquipamentos();
    }
});
