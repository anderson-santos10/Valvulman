/**
 * VALVULMAN — comportamentos genéricos do Design System (sem regra de negócio).
 */
document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.getElementById("sidebar");
    const mobileToggleBtn = document.getElementById("mobileToggleBtn");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const userMenu = document.getElementById("userMenu");
    const userMenuToggle = document.getElementById("userMenuToggle");
    const userMenuPanel = document.getElementById("userMenuPanel");
    const DRAWER_MAX = 1023;

    const isDrawerViewport = () => window.innerWidth <= DRAWER_MAX;

    const closeUserMenu = () => {
        if (!userMenuPanel || !userMenuToggle) return;
        userMenuPanel.hidden = true;
        userMenuToggle.setAttribute("aria-expanded", "false");
    };

    const syncSubmenuAria = () => {
        if (!sidebar) return;
        sidebar.querySelectorAll(".sidebar-item-has-submenu").forEach((item) => {
            const toggle = item.querySelector(".submenu-toggle");
            const submenu = item.querySelector(".sidebar-submenu");
            const isOpen = item.classList.contains("open");
            if (toggle) toggle.setAttribute("aria-expanded", isOpen.toString());
            if (submenu) submenu.setAttribute("aria-hidden", (!isOpen).toString());
        });
    };

    const syncDrawerA11y = () => {
        if (!sidebar) return;
        const drawerClosed = isDrawerViewport() && !sidebar.classList.contains("is-mobile-open");
        sidebar.setAttribute("aria-hidden", drawerClosed ? "true" : "false");
    };

    const closeMobileSidebar = () => {
        if (!sidebar) return;
        sidebar.classList.remove("is-mobile-open");
        document.body.classList.remove("sidebar-mobile-open");
        if (sidebarOverlay) {
            sidebarOverlay.classList.remove("is-active");
            sidebarOverlay.setAttribute("aria-hidden", "true");
        }
        if (mobileToggleBtn) {
            mobileToggleBtn.setAttribute("aria-expanded", "false");
            mobileToggleBtn.setAttribute("aria-label", "Abrir menu de navegação");
        }
        syncSubmenuAria();
        syncDrawerA11y();
    };

    const openMobileSidebar = () => {
        sidebar.classList.add("is-mobile-open");
        document.body.classList.add("sidebar-mobile-open");
        if (sidebarOverlay) {
            sidebarOverlay.classList.add("is-active");
            sidebarOverlay.setAttribute("aria-hidden", "false");
        }
        if (mobileToggleBtn) {
            mobileToggleBtn.setAttribute("aria-expanded", "true");
            mobileToggleBtn.setAttribute("aria-label", "Fechar menu de navegação");
        }
        syncSubmenuAria();
        syncDrawerA11y();
    };

    if (sidebar && sidebar.dataset.navReady !== "1") {
        sidebar.dataset.navReady = "1";
        const submenuItems = sidebar.querySelectorAll(".sidebar-item-has-submenu");
        submenuItems.forEach((item) => {
            if (item.querySelector(".submenu-link.is-active")) item.classList.add("open");
        });
        syncSubmenuAria();

        sidebar.querySelectorAll(".submenu-toggle").forEach((toggle) => {
            toggle.addEventListener("click", (event) => {
                event.preventDefault();
                const parent = toggle.closest(".sidebar-item-has-submenu");
                if (!parent) return;
                const willOpen = !parent.classList.contains("open");
                submenuItems.forEach((item) => {
                    if (item !== parent) item.classList.remove("open");
                });
                parent.classList.toggle("open", willOpen);
                syncSubmenuAria();
            });
        });

        if (mobileToggleBtn) {
            mobileToggleBtn.addEventListener("click", () => {
                if (sidebar.classList.contains("is-mobile-open")) closeMobileSidebar();
                else openMobileSidebar();
            });
        }
        if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeMobileSidebar);
        window.addEventListener("resize", () => {
            if (!isDrawerViewport()) closeMobileSidebar();
            else syncDrawerA11y();
        });
        syncDrawerA11y();
    }

    if (userMenuToggle && userMenuPanel) {
        userMenuToggle.addEventListener("click", (event) => {
            event.stopPropagation();
            const open = userMenuPanel.hidden;
            userMenuPanel.hidden = !open;
            userMenuToggle.setAttribute("aria-expanded", open.toString());
        });
    }
    document.addEventListener("click", (event) => {
        if (userMenu && !userMenu.contains(event.target)) closeUserMenu();
    });

    document.querySelectorAll("[data-vm-tabs]").forEach((root) => {
        const tabs = root.querySelectorAll("[role='tab']");
        const panels = root.querySelectorAll("[role='tabpanel']");
        tabs.forEach((tab) => {
            tab.addEventListener("click", () => {
                const id = tab.getAttribute("aria-controls");
                tabs.forEach((item) => item.setAttribute("aria-selected", item === tab ? "true" : "false"));
                panels.forEach((panel) => {
                    panel.hidden = panel.id !== id;
                });
            });
        });
    });

    const closeModal = (modal) => {
        modal.hidden = true;
        document.body.classList.remove("vm-modal-open");
    };

    document.querySelectorAll("[data-vm-open]").forEach((button) => {
        button.addEventListener("click", () => {
            const modal = document.getElementById(button.getAttribute("data-vm-open"));
            if (!modal) return;
            modal.hidden = false;
            document.body.classList.add("vm-modal-open");
            const closeBtn = modal.querySelector("[data-vm-close]");
            if (closeBtn) closeBtn.focus();
        });
    });

    document.querySelectorAll("[data-vm-close]").forEach((button) => {
        button.addEventListener("click", () => {
            const modal = button.closest(".vm-modal, .vm-drawer");
            if (modal) closeModal(modal);
        });
    });

    document.querySelectorAll(".vm-toggle").forEach((toggle) => {
        toggle.addEventListener("click", () => {
            const pressed = toggle.getAttribute("aria-pressed") === "true";
            toggle.setAttribute("aria-pressed", pressed ? "false" : "true");
        });
    });

    document.querySelectorAll("[data-vm-toast]").forEach((button) => {
        button.addEventListener("click", () => {
            window.vmToast(button.getAttribute("data-vm-toast") || "");
        });
    });

    document.querySelectorAll("table.tabela-os:not(.tabela-os--wide)").forEach((table) => {
        const labels = Array.from(table.querySelectorAll("thead th")).map((th) => th.textContent.trim());
        table.querySelectorAll("tr").forEach((row) => {
            const cells = Array.from(row.children);
            cells.forEach((cell, index) => {
                if (labels[index] && !cell.getAttribute("data-label")) {
                    cell.setAttribute("data-label", labels[index]);
                }
            });
            if (cells.length >= 5) {
                cells.slice(3, -2).forEach((cell) => cell.classList.add("col-secondary"));
            }
        });
    });

    document.querySelectorAll("[data-vm-copy]").forEach((button) => {
        button.addEventListener("click", async () => {
            const value = button.getAttribute("data-vm-copy") || "";
            try {
                await navigator.clipboard.writeText(value);
                window.vmToast("Copiado.");
            } catch (error) {
                window.vmToast("Não foi possível copiar.");
            }
        });
    });

    window.vmToast = (message) => {
        let region = document.querySelector(".vm-toast-region");
        if (!region) {
            region = document.createElement("div");
            region.className = "vm-toast-region";
            region.setAttribute("aria-live", "polite");
            document.body.appendChild(region);
        }
        const toast = document.createElement("div");
        toast.className = "vm-toast";
        toast.textContent = message;
        region.appendChild(toast);
        window.setTimeout(() => toast.remove(), 3200);
    };

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        closeUserMenu();
        if (isDrawerViewport()) closeMobileSidebar();
        document.querySelectorAll(".vm-modal:not([hidden]), .vm-drawer:not([hidden])").forEach(closeModal);
    });
});
