document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("clienteSearch");

    if (!searchInput) return;

    // Restaura o foco e posiciona o cursor no final do texto após o reload
    const urlParams = new URLSearchParams(window.location.search);
    const queryAtual = urlParams.get("q");

    if (queryAtual !== null) {
        searchInput.value = queryAtual;
        searchInput.focus();
        searchInput.setSelectionRange(queryAtual.length, queryAtual.length);
    }

    let timer;

    /**
     * Atualiza os parâmetros da URL e recarrega a página (Debounce 400ms)
     */
    searchInput.addEventListener("input", function () {
        clearTimeout(timer);

        timer = setTimeout(() => {
            const valor = searchInput.value.trim();
            const url = new URL(window.location.href);

            if (valor) {
                url.searchParams.set("q", valor);
            } else {
                url.searchParams.delete("q");
            }

            url.searchParams.delete("page"); // Reseta para a página 1 em nova busca
            window.location.href = url.toString();
        }, 400);
    });

    /**
     * Limpa a pesquisa e reseta a URL ao pressionar ESC
     */
    searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            searchInput.value = "";
            const url = new URL(window.location.href);

            url.searchParams.delete("q");
            url.searchParams.delete("page");
            window.location.href = url.toString();
        }
    });

    /**
     * Atalho "/" para focar na pesquisa
     */
    document.addEventListener("keydown", function (event) {
        const activeTag = document.activeElement.tagName;

        if (
            event.key === "/" &&
            document.activeElement !== searchInput &&
            !["INPUT", "TEXTAREA", "SELECT"].includes(activeTag)
        ) {
            event.preventDefault();
            searchInput.focus();
        }
    });
});