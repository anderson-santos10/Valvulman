document.addEventListener("DOMContentLoaded", function () {
    const botao = document.getElementById("btn-imprimir-certificado");
    if (!botao) {
        return;
    }
    botao.addEventListener("click", function (event) {
        event.preventDefault();
        window.print();
    });
});
