# Usuários, permissões e auditoria

## Superusuário

```bash
python manage.py createsuperuser
```

O superusuário Django (`is_superuser=True`) acessa todas as telas e ações, independentemente de grupo.

## Grupos

```bash
python manage.py migrate
python manage.py seed_permissoes
```

O comando é idempotente: não duplica grupos. Deve ser executado depois das migrations (as permissões customizadas de calibração, OS, orçamento e financeiro nascem na migration `servicos.0014`).

Pode ser executado várias vezes. Cria ou atualiza:

| Grupo | Papel |
| --- | --- |
| ADMINISTRADOR | Tudo, inclusive usuários e auditoria |
| TECNICO | Cadastros técnicos, calibração, emissão de certificado |
| COMERCIAL | Clientes, orçamentos, geração de OS |
| FINANCEIRO | Cobranças e pagamentos |
| CONSULTA | Somente visualização |

O grupo ADMINISTRADOR recebe as permissões dos apps `clientes`, `servicos`, `acesso` e `auth`. Não é o mesmo que superusuário.

Administração de usuários: `/usuarios/` (quem tiver `auth.view_user` / `add_user` / `change_user`).

Auditoria: `/auditoria/` (`acesso.view_registroauditoria`). Registros não são editáveis nem excluíveis pela interface.

A autorização está nas views (`PermissionRequiredMixin`). Esconder botão no menu não é segurança.

## Reset para simulação

`python manage.py reset_simulacao` apaga dados de negócio e **preserva** usuários, grupos e permissões. Exige a confirmação `RESETAR`. Bloqueado se `DEBUG=False`. Ver `docs/simulacao.md`.
