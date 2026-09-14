# Reset para simulação

Limpa **somente os dados de negócio** do banco de desenvolvimento, para começar uma operação do zero com os mesmos usuários.

```bash
python manage.py reset_simulacao
```

Quando solicitado, digite exatamente:

```text
RESETAR
```

ENTER, `sim` ou qualquer outro texto **não** executa o reset.

Em scripts de teste (nunca em produção):

```bash
python manage.py reset_simulacao --confirmar RESETAR
```

## O que é apagado

Clientes, válvulas, instrumentos, padrões, OS e itens, calibrações, pontos, execuções de válvula, certificados, orçamentos, relatórios técnicos legados, cobranças, pagamentos e registros de auditoria operacional.

## O que é preservado

- usuários (username, senha, e-mail, flags, grupos e permissões)
- grupos e permissões do Django
- content types
- sessões (`django_session`)
- estrutura do banco e migrations
- código e configurações

Nenhum cliente, equipamento ou OS de demonstração é recriado.

## Dados DEMO de metrologia (desenvolvimento)

Após o reset, não há padrão de medição. Em desenvolvimento:

```bash
python manage.py seed_metrologia_demo
```

Cria/atualiza somente `PAD-DEMO-001` (Padrão de Pressão Demonstrativo), sem certificado nem validade. O comando imprime os textos livres sugeridos para procedimento (`PROC-DEMO-MAN-001`) e critério. **Não afirma rastreabilidade.** Bloqueado com `DEBUG=False`.

## Produção

O comando **não roda** com `DEBUG=False`. Não use em produção.

Não use `flush` nem apague o arquivo SQLite: isso removeria usuários e permissões.
