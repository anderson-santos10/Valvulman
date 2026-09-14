document.addEventListener("DOMContentLoaded", function () {

    const tbody = document.getElementById("valvulas-tbody");
    const btnAdd = document.getElementById("btn-add-item");
    const btnRemove = document.getElementById("btn-remove-item");
    const clienteSelect = document.getElementById("cliente");
    const cadastroSelect = document.getElementById("valvula-cadastro-select");
    const btnIncluirCadastro = document.getElementById("btn-incluir-cadastro");
    const formReport = document.querySelector(".form-report");
    const valvulasUrlTemplate = formReport
        ? formReport.getAttribute("data-valvulas-url")
        : "";

    if (!tbody || !btnAdd || !btnRemove) {
        console.error("Elementos da tabela de válvulas não encontrados.");
        return;
    }

    function criarLinha(dados) {
        dados = dados || {};
        const numeroItem = tbody.querySelectorAll("tr").length + 1;
        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td>
                <input type="hidden" name="valvula_cadastro[]" value="">
                <input type="text" name="valvula_item[]" value="${numeroItem}" readonly class="campo-item">
            </td>
            <td><input type="text" name="valvula_serie[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_tag[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_diametro[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_modelo[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_fabricante[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_pressao[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_servico[]" autocomplete="off"></td>
            <td><input type="text" name="valvula_observacao[]" autocomplete="off"></td>
        `;

        tbody.appendChild(tr);

        const campo = (name) => tr.querySelector(`[name="${name}"]`);
        if (dados.id) campo("valvula_cadastro[]").value = dados.id;
        if (dados.numero_serie) campo("valvula_serie[]").value = dados.numero_serie;
        if (dados.tag) campo("valvula_tag[]").value = dados.tag;
        if (dados.diametro) campo("valvula_diametro[]").value = dados.diametro;
        if (dados.modelo) campo("valvula_modelo[]").value = dados.modelo;
        if (dados.fabricante) campo("valvula_fabricante[]").value = dados.fabricante;
        if (dados.pressao) campo("valvula_pressao[]").value = dados.pressao;

        atualizarNumeracao();
        return tr;
    }

    function adicionarValvula() {
        const tr = criarLinha();
        const primeiroCampo = tr.querySelector('input[name="valvula_serie[]"]');
        if (primeiroCampo) {
            primeiroCampo.focus();
        }
    }

    function removerValvula() {
        const linhas = tbody.querySelectorAll("tr");
        if (linhas.length <= 1) {
            return;
        }
        const ultimaLinha = tbody.lastElementChild;
        if (ultimaLinha) {
            ultimaLinha.remove();
        }
        atualizarNumeracao();
    }

    function atualizarNumeracao() {
        const linhas = tbody.querySelectorAll("tr");
        linhas.forEach(function (linha, index) {
            const campoItem = linha.querySelector('input[name="valvula_item[]"]');
            if (campoItem) {
                campoItem.value = index + 1;
            }
        });
    }

    function urlValvulasCliente(clienteId) {
        if (!valvulasUrlTemplate) {
            return "";
        }
        return valvulasUrlTemplate.replace("/0/", `/${clienteId}/`);
    }

    function resetarSelectCadastro(mensagem) {
        if (!cadastroSelect) {
            return;
        }
        cadastroSelect.innerHTML = "";
        const option = document.createElement("option");
        option.value = "";
        option.textContent = mensagem;
        cadastroSelect.appendChild(option);
        cadastroSelect.disabled = true;
        if (btnIncluirCadastro) {
            btnIncluirCadastro.disabled = true;
        }
    }

    function carregarValvulasDoCliente(clienteId) {
        if (!cadastroSelect) {
            return;
        }
        if (!clienteId) {
            resetarSelectCadastro("Selecione o cliente para listar as válvulas");
            return;
        }

        const url = urlValvulasCliente(clienteId);
        if (!url) {
            return;
        }

        resetarSelectCadastro("Carregando...");

        fetch(url, { headers: { Accept: "application/json" } })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Falha ao carregar válvulas.");
                }
                return response.json();
            })
            .then((payload) => {
                cadastroSelect.innerHTML = "";
                const placeholder = document.createElement("option");
                placeholder.value = "";
                const itens = payload.valvulas || [];
                placeholder.textContent = itens.length
                    ? "Selecione uma válvula cadastrada"
                    : "Cliente sem válvulas ativas";
                cadastroSelect.appendChild(placeholder);
                itens.forEach((valvula) => {
                    const option = document.createElement("option");
                    option.value = String(valvula.id);
                    option.textContent = valvula.label;
                    option.dataset.numeroSerie = valvula.numero_serie || "";
                    option.dataset.tag = valvula.tag || "";
                    option.dataset.diametro = valvula.diametro || "";
                    option.dataset.modelo = valvula.modelo || "";
                    option.dataset.fabricante = valvula.fabricante || "";
                    option.dataset.pressao = valvula.pressao || "";
                    cadastroSelect.appendChild(option);
                });
                cadastroSelect.disabled = itens.length === 0;
                if (btnIncluirCadastro) {
                    btnIncluirCadastro.disabled = itens.length === 0;
                }
            })
            .catch(() => {
                resetarSelectCadastro("Não foi possível carregar as válvulas");
            });
    }

    btnAdd.addEventListener("click", function (event) {
        event.preventDefault();
        adicionarValvula();
    });

    btnRemove.addEventListener("click", function (event) {
        event.preventDefault();
        removerValvula();
    });

    if (clienteSelect) {
        clienteSelect.addEventListener("change", function () {
            carregarValvulasDoCliente(clienteSelect.value);
        });
        if (clienteSelect.value) {
            carregarValvulasDoCliente(clienteSelect.value);
        }
    }

    if (btnIncluirCadastro && cadastroSelect) {
        btnIncluirCadastro.addEventListener("click", function (event) {
            event.preventDefault();
            const option = cadastroSelect.options[cadastroSelect.selectedIndex];
            if (!option || !option.value) {
                return;
            }
            criarLinha({
                id: option.value,
                numero_serie: option.dataset.numeroSerie,
                tag: option.dataset.tag,
                diametro: option.dataset.diametro,
                modelo: option.dataset.modelo,
                fabricante: option.dataset.fabricante,
                pressao: option.dataset.pressao,
            });
        });
    }

    if (tbody.querySelectorAll("tr").length === 0) {
        adicionarValvula();
    } else {
        atualizarNumeracao();
    }

});
