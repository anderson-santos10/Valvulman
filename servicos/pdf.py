import base64
import logging
import os
import re
from io import BytesIO
from pathlib import Path

from django.contrib.staticfiles.finders import find
from django.template.loader import render_to_string
from pypdf import PdfReader, PdfWriter

from .validacao import qr_code_data_uri, url_validacao_publica

logger = logging.getLogger(__name__)

CSS_CERTIFICADO = "css/certificados_ensaio.css"
CSS_CERTIFICADO_PDF = "css/certificados_ensaio_pdf.css"
LOGO_CERTIFICADO = "img/logo_valvulman.svg"


class PdfGenerationError(Exception):
    """Falha ao montar ou renderizar o PDF oficial."""


def contexto_documento_certificado(certificado, request=None, **extra):
    calibracao = certificado.calibracao
    url_validacao = url_validacao_publica(
        certificado.token_validacao,
        request=request,
    )
    contexto = {
        "certificado": certificado,
        "calibracao": calibracao,
        "instrumento": calibracao.instrumento,
        "cliente": calibracao.instrumento.cliente,
        "resumo": calibracao.resumo_aceitacao(),
        "url_validacao": url_validacao,
        "certificado_qr_src": qr_code_data_uri(url_validacao),
    }
    contexto.update(extra)
    return contexto


def nome_arquivo_pdf(numero):
    seguro = re.sub(r"[^A-Za-z0-9._-]", "", numero or "")
    if not seguro:
        raise PdfGenerationError("Número de certificado inválido para o arquivo PDF.")
    return f"Certificado_{seguro}.pdf"


def gerar_pdf_certificado(certificado):
    try:
        html = _renderizar_html(certificado)
        pdf_bytes = _html_para_pdf(html)
        return _aplicar_metadados(pdf_bytes, certificado)
    except PdfGenerationError:
        raise
    except Exception as exc:
        logger.exception(
            "Falha inesperada ao gerar PDF do certificado %s (calibração %s).",
            getattr(certificado, "numero", ""),
            getattr(getattr(certificado, "calibracao", None), "numero", ""),
        )
        raise PdfGenerationError("Falha ao gerar PDF do certificado.") from exc


def _renderizar_html(certificado):
    css = "\n".join(
        (
            _ler_estatico(CSS_CERTIFICADO),
            _ler_estatico(CSS_CERTIFICADO_PDF),
        )
    )
    contexto = contexto_documento_certificado(
        certificado,
        certificado_css=css,
        certificado_logo_src=_data_uri_logo(_caminho_estatico(LOGO_CERTIFICADO)),
        modo_impressao=True,
    )
    return render_to_string("servicos/pdf_certificado_ensaio.html", contexto)


def _html_para_pdf(html):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PdfGenerationError(
            "A biblioteca Playwright não está instalada."
        ) from exc

    argumentos = ["--disable-dev-shm-usage"]
    if os.environ.get("PLAYWRIGHT_CHROMIUM_NO_SANDBOX") == "1":
        argumentos.append("--no-sandbox")

    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(
                headless=True,
                args=argumentos,
            )
            try:
                pagina = navegador.new_page(viewport={"width": 1200, "height": 1600})
                pagina.set_content(html, wait_until="load")
                return pagina.pdf(
                    format="A4",
                    landscape=False,
                    print_background=True,
                    prefer_css_page_size=True,
                    display_header_footer=False,
                    margin={
                        "top": "0",
                        "right": "0",
                        "bottom": "0",
                        "left": "0",
                    },
                )
            finally:
                navegador.close()
    except PlaywrightError as exc:
        logger.exception("Playwright falhou ao gerar o PDF do certificado.")
        raise PdfGenerationError("Falha ao renderizar o PDF do certificado.") from exc
    except OSError as exc:
        logger.exception("Chromium do Playwright indisponível para gerar PDF.")
        raise PdfGenerationError(
            "O navegador de geração de PDF não está disponível."
        ) from exc


def _aplicar_metadados(pdf_bytes, certificado):
    try:
        leitor = PdfReader(BytesIO(pdf_bytes))
        escritor = PdfWriter()
        escritor.append(leitor)
        escritor.add_metadata(
            {
                "/Title": f"Certificado de Calibração {certificado.numero}",
                "/Author": "Valvulman",
                "/Subject": "Certificado de Calibração",
                "/Creator": "Valvulman",
            }
        )
        saida = BytesIO()
        escritor.write(saida)
        return saida.getvalue()
    except Exception:
        logger.exception(
            "Não foi possível gravar metadados do PDF %s; o arquivo gerado foi mantido.",
            certificado.numero,
        )
        return pdf_bytes


def _caminho_estatico(relativo):
    encontrado = find(relativo)
    if not encontrado:
        raise PdfGenerationError(f"Arquivo estático não encontrado: {relativo}")
    return Path(encontrado)


def _ler_estatico(relativo):
    return _caminho_estatico(relativo).read_text(encoding="utf-8")


def _data_uri_logo(caminho):
    svg = caminho.read_text(encoding="utf-8")
    if "width=" not in svg[:180]:
        svg = svg.replace(
            "<svg ",
            '<svg width="56" height="56" ',
            1,
        )
    conteudo = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{conteudo}"
