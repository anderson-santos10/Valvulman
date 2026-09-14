# Valvulman

Sistema Django de gestão técnica.

## Usuários, permissões e auditoria

O sistema usa o `User` padrão do Django (sem `AUTH_USER_MODEL` customizado), grupos e permissões nativas. Superusuário tem acesso total, mesmo sem grupo.

Perfis (`python manage.py seed_permissoes`, idempotente):

- **ADMINISTRADOR** — acesso completo, inclusive usuários e auditoria
- **TECNICO** — operação técnica (instrumentos, calibração, certificados); sem financeiro nem usuários
- **COMERCIAL** — clientes, orçamentos e OS comercial; sem pagamentos nem ensaios
- **FINANCEIRO** — cobranças e pagamentos; sem alterar dados técnicos
- **CONSULTA** — somente leitura; POST de alteração retorna 403

O grupo ADMINISTRADOR não substitui o superusuário: `createsuperuser` continua sendo a conta com `is_superuser=True`.

Áreas internas:

- `/usuarios/` — cadastro, edição, ativar/inativar (POST + CSRF)
- `/auditoria/` — trilha somente leitura

Detalhes em `docs/permissoes.md`.

## Design System

A interface usa tokens `--vm-*` em `static/css/design-system.css`, layout em `layout.css` e adaptação das telas em `pages.css`. Catálogo interno (staff/superusuário): `/design-system/`.

Documentos oficiais A4 (certificados, OS, orçamentos, cobranças) mantêm CSS de impressão próprio.

## Geração de PDF

O certificado de calibração da Etapa 8A é exportado em PDF A4 com Playwright/Chromium.

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

No Linux de produção, instale também as dependências do Chromium (`python -m playwright install-deps chromium`). Detalhes em `docs/pdf.md`.

## Validação pública e QR Code

Defina `PUBLIC_BASE_URL` (sem barra no final) para a URL usada no QR Code, por exemplo `https://seu-dominio`. Sem esse valor, o sistema usa o host da requisição; em desenvolvimento local, o fallback é `http://127.0.0.1:8000`.

O QR Code é gerado localmente com **segno** (SVG). O cálculo de validade em meses usa **python-dateutil**. Não há dependência extra de sistema para o QR Code no Windows, Linux ou Railway.

## Reset para simulação

Para zerar dados de negócio no desenvolvimento, preservando usuários e permissões:

```bash
python manage.py reset_simulacao
```

Confirme digitando `RESETAR`. Detalhes em `docs/simulacao.md`. **Não usar em produção** (`DEBUG=False` bloqueia o comando).

## Padrões de medição

O cadastro mestre `PadraoMedicao` é recurso interno do laboratório (não pertence ao cliente). A calibração guarda a FK e um snapshot em `padrao_utilizado`.

- Sem `data_validade` no padrão, o uso é permitido e o sistema **não afirma prazo**.
- Com validade, a data da calibração deve ser menor ou igual à validade do padrão.
- Padrão inativo não entra em nova calibração; o histórico permanece.

Em desenvolvimento, `python manage.py seed_metrologia_demo` cria `PAD-DEMO-001` para simulação. Procedimento e critério são texto livre no ensaio. O comando exige `DEBUG=True` e não afirma rastreabilidade. Ver `docs/simulacao.md`.
