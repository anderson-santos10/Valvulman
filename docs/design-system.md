# Design System Valvulman

Tokens CSS em `static/css/design-system.css`. Identidade por empresa no futuro: altere `--tenant-primary` e `--tenant-accent` (não implementado nesta etapa).

```bash
# Catálogo (usuários staff ou superusuário)
/design-system/
```

O `templates/base.html` carrega, nesta ordem: `design-system.css`, `layout.css`, `pages.css`, `print.css`. Não usar `@import` em `base.css`.

- `static/css/design-system.css` — tokens e componentes
- `static/css/layout.css` — sidebar 240px + topbar 64px
- `static/css/pages.css` — telas existentes
- `static/css/print.css` — oculta chrome na impressão da UI
- `static/js/design-system.js` — modal, tabs, toast, drawer, sidebar mobile

Impressão A4 oficial: `imprimir_*.css`, `certificados_ensaio_pdf.css`, `certificado_calibracao.css`.
