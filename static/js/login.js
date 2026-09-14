document.addEventListener("DOMContentLoaded", () => {
    const passwordInput = document.getElementById("id_password");
    const toggleButton = document.getElementById("passwordToggle");
    const eyeOpen = document.getElementById("eyeOpen");
    const eyeClosed = document.getElementById("eyeClosed");

    if (!passwordInput || !toggleButton) {
        return;
    }

    toggleButton.addEventListener("click", () => {
        const showingPassword = passwordInput.type === "text";

        passwordInput.type = showingPassword ? "password" : "text";
        toggleButton.setAttribute(
            "aria-label",
            showingPassword ? "Mostrar senha" : "Ocultar senha"
        );

        if (eyeOpen) {
            eyeOpen.classList.toggle("is-hidden", !showingPassword);
        }
        if (eyeClosed) {
            eyeClosed.classList.toggle("is-hidden", showingPassword);
        }
    });
});
