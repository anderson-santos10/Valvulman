# Geração de PDF do certificado de calibração

O PDF oficial reutiliza o documento HTML da Etapa 8A (`_documento_certificado_ensaio.html`). A metrologia não é recalculada.

## Biblioteca

O Valvulman usa **Playwright 1.55** com **Chromium** para converter o HTML/CSS já validado em PDF A4.

**WeasyPrint** foi avaliado e descartado neste ambiente: no Windows exige GTK/Pango/Cairo (`libgobject-2.0-0`), o que torna a instalação frágil. Playwright renderiza o mesmo CSS (incluindo grade, SVG e UTF-8) no Windows de desenvolvimento e no Linux de produção.

**pypdf** grava apenas metadados (título, autor, assunto) no arquivo já gerado.

## Instalação local (Windows)

No ambiente virtual:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Teste:

```bash
python manage.py test servicos.test_certificados
```

O PDF é gerado sob demanda. Não é gravado no banco nem em pasta pública.

## Produção Linux / Railway

Dependências Python: as mesmas de `requirements.txt` (`playwright`, `pypdf`, `segno`, `python-dateutil`).

O QR Code do certificado é SVG gerado localmente (segno). Não há biblioteca extra de sistema para o QR Code.

Depois do build:

```bash
python -m playwright install chromium
python -m playwright install-deps chromium
```

Em imagens Debian/Ubuntu, `install-deps` instala bibliotecas do sistema (NSS, ATK, GBM, ALSA, etc.).

Se o Chromium recusar o sandbox no container, defina:

```text
PLAYWRIGHT_CHROMIUM_NO_SANDBOX=1
```

Não use essa variável no Windows local, salvo diagnóstico pontual.

O Chromium **não** é baixado automaticamente em cada requisição. A instalação é um passo de ambiente (`python -m playwright install chromium`), uma vez por máquina/imagem.

Em `DEBUG=True`, a tela do certificado pode incluir a causa da falha (por exemplo, Chromium ausente) junto da mensagem amigável. Em produção (`DEBUG=False`) o usuário vê apenas:

```text
Não foi possível gerar o PDF do certificado. Tente novamente.
```

O traceback e a causa original vão para o log do servidor.

## Problemas comuns

| Sintoma | Causa provável | Ação |
| --- | --- | --- |
| Erro ao gerar PDF / Chromium não encontrado | `playwright install chromium` não foi executado | Instalar o Chromium do Playwright |
| Falha no Railway/Docker | Faltam libs do sistema ou `/dev/shm` pequeno | `playwright install-deps` e `--disable-dev-shm-usage` (já usado) |
| Logo ausente | Arquivo estático não encontrado pelos finders | Conferir `static/img/logo_valvulman.svg` |
