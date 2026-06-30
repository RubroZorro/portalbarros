import base64
import json
import logging
import re
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='email')
log = logging.getLogger(__name__)

BREVO_URL = 'https://api.brevo.com/v3/smtp/email'


# ──────────────────────────────────────────────
# Core Brevo
# ──────────────────────────────────────────────

def _brevo_post(api_key: str, payload: dict) -> bool:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BREVO_URL, data=data, method='POST')
    req.add_header('api-key', api_key)
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        log.error(f'Brevo HTTP {e.code}: {body}')
        return False
    except Exception as e:
        log.error(f'Brevo erro: {e}')
        return False


def _build_payload(from_email: str, destinatarios: list[str],
                   assunto: str, corpo_html: str,
                   anexos: list[tuple] | None) -> dict:
    payload = {
        'sender': {'name': 'Portal Barros & Barros', 'email': from_email},
        'to': [{'email': e} for e in destinatarios],
        'subject': assunto,
        'htmlContent': corpo_html,
        'textContent': _strip_html(corpo_html) or ' ',
    }
    if anexos:
        payload['attachment'] = [
            {
                'name': filename,
                'content': base64.b64encode(data).decode('ascii'),
            }
            for filename, data, content_type in anexos
        ]
    return payload


# ──────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────

def _corpo_html(tipo: str, competencia: str, n_anexos: int = 1) -> tuple[str, str]:
    """Retorna (titulo, html_completo) para o tipo de envio."""
    if tipo == 'boleto':
        titulo = 'Boleto de Honorários Contábeis'
        corpo = f'''
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">Prezado(a),</p>
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">
          Encaminhamos em anexo o <strong>Boleto de Honorários Contábeis</strong>
          referente à competência de <strong>{competencia}</strong>.
        </p>
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">
          Pedimos que o pagamento seja efetuado até a <strong>data de vencimento</strong>
          indicada no documento.
        </p>
        <p style="margin:0;font-size:0.93rem;color:#374151;">
          Em caso de dúvidas, nossa equipe está à disposição.
        </p>'''
    elif tipo == 'recibo':
        titulo = 'Recibo de Pagamento'
        corpo = f'''
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">Prezado(a),</p>
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">
          Segue em anexo o <strong>Recibo de Pagamento</strong> dos honorários contábeis
          referente à competência de <strong>{competencia}</strong>,
          confirmando o recebimento dos honorários.
        </p>
        <p style="margin:0;font-size:0.93rem;color:#374151;">
          Guarde este documento para o seu controle financeiro.
        </p>'''
    else:
        titulo = 'Documentos Fiscais' if n_anexos > 1 else 'Documento Fiscal'
        arq = 'os documentos fiscais' if n_anexos > 1 else 'o documento fiscal'
        ref = 'referentes' if n_anexos > 1 else 'referente'
        corpo = f'''
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">Prezado(a),</p>
        <p style="margin:0 0 14px;font-size:0.93rem;color:#374151;">
          Disponibilizamos em anexo {arq} {ref} à competência de
          <strong>{competencia}</strong>.
        </p>
        <p style="margin:0;font-size:0.93rem;color:#374151;">
          Os arquivos também estão disponíveis para download na seção
          <strong>Documentos</strong> do portal a qualquer momento.
        </p>'''

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:32px 0;">
  <tr><td align="center">
  <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);max-width:560px;">
    <tr><td style="background:linear-gradient(135deg,#1B2D6B 0%,#243d8f 100%);padding:32px 40px;">
      <table cellpadding="0" cellspacing="0"><tr>
        <td style="font-family:Georgia,serif;font-size:2.2rem;font-weight:700;letter-spacing:-1px;">
          <span style="color:#C9A227;">B</span><span style="color:#ffffff;">B</span>
        </td>
        <td style="padding-left:14px;border-left:1px solid rgba(255,255,255,0.25);">
          <div style="font-size:0.6rem;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:#C9A227;margin-bottom:3px;">Barros &amp; Barros</div>
          <div style="font-size:0.6rem;color:rgba(255,255,255,0.65);text-transform:uppercase;letter-spacing:0.12em;">Contabilidade</div>
        </td>
      </tr></table>
      <div style="margin-top:22px;">
        <div style="color:#ffffff;font-size:1.2rem;font-weight:700;line-height:1.3;">{titulo}</div>
        <div style="color:rgba(255,255,255,0.6);font-size:0.8rem;margin-top:5px;">Competência: {competencia}</div>
      </div>
    </td></tr>
    <tr><td style="padding:36px 40px 28px;">{corpo}</td></tr>
    <tr><td style="padding:0 40px;"><div style="height:1px;background:#e5e7eb;"></div></td></tr>
    <tr><td style="padding:22px 40px 30px;">
      <p style="margin:0 0 6px;font-size:0.75rem;color:#6b7280;">
        Este é um e-mail automático enviado pelo <strong>Portal Barros &amp; Barros</strong>.
        Por favor, não responda a este e-mail.
      </p>
      <p style="margin:0;font-size:0.75rem;color:#9ca3af;">
        Dúvidas? Fale conosco pelo WhatsApp:
        <a href="https://wa.me/5581996876093" style="color:#1B2D6B;text-decoration:none;font-weight:600;">(81) 99687-6093</a>
      </p>
    </td></tr>
  </table>
  </td></tr>
</table>
</body></html>'''

    return titulo, html


# ──────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────

def send_email(
    destinatarios: list[str],
    assunto: str,
    corpo_html: str,
    anexos: list[tuple] | None = None,
) -> bool:
    """Agenda envio em segundo plano. Retorna True se credenciais configuradas."""
    api_key   = current_app.config.get('BREVO_API_KEY')
    from_email = current_app.config.get('MAIL_FROM', 'portal@barrosebarroscontabilidade.com.br')
    if not api_key:
        current_app.logger.warning('BREVO_API_KEY não configurada — email não enviado.')
        return False

    payload = _build_payload(from_email, destinatarios, assunto, corpo_html, anexos)

    def _task():
        if not _brevo_post(api_key, payload):
            log.error(f'Falha Brevo para {destinatarios}')

    _pool.submit(_task)
    return True


def send_email_tipo(
    destinatarios: list[str],
    tipo: str,
    competencia: str,
    razao_social: str,
    anexos: list[tuple] | None = None,
) -> bool:
    """
    Envia email formatado por tipo (boleto/recibo/documento).
    competencia: ex. 'Junho/2026'
    """
    n = len(anexos) if anexos else 1
    titulo, html = _corpo_html(tipo, competencia, n)
    assunto = f'{titulo} — {competencia} | {razao_social}'
    return send_email(destinatarios, assunto, html, anexos)


def send_emails_lote(
    lote: list[dict],
    username: str,
    password: str,
) -> None:
    """
    Envia lote em 2 threads paralelas (uma conexão Brevo por thread).
    Cada item: {destinatarios, assunto, corpo_html, anexos}.
    """
    if not lote:
        return

    from flask import current_app as _app
    api_key    = _app.config.get('BREVO_API_KEY', '')
    from_email = _app.config.get('MAIL_FROM', 'portal@barrosebarroscontabilidade.com.br')

    if not api_key:
        log.warning('BREVO_API_KEY não configurada — lote não enviado.')
        return

    mid = (len(lote) + 1) // 2
    batches = [lote[:mid], lote[mid:]]

    def _batch_task(batch):
        for item in batch:
            payload = _build_payload(
                from_email,
                item['destinatarios'],
                item['assunto'],
                item['corpo_html'],
                item.get('anexos'),
            )
            if not _brevo_post(api_key, payload):
                log.error(f'Falha Brevo lote para {item["destinatarios"]}')

    for batch in batches:
        if batch:
            _pool.submit(_batch_task, batch)


def send_emails_lote_tipo(
    lote: list[dict],
    tipo: str,
    mes_nome: str,
    ano: int,
) -> None:
    """
    Envia lote formatado por tipo. Cada item: {destinatarios, razao, arquivos}.
    """
    from flask import current_app as _app
    api_key    = _app.config.get('BREVO_API_KEY', '')
    from_email = _app.config.get('MAIL_FROM', 'portal@barrosebarroscontabilidade.com.br')

    if not api_key or not lote:
        return

    competencia = f'{mes_nome}/{ano}'
    mid = (len(lote) + 1) // 2
    batches = [lote[:mid], lote[mid:]]

    def _batch_task(batch):
        for item in batch:
            n = len(item.get('arquivos') or [])
            titulo, html = _corpo_html(tipo, competencia, max(n, 1))
            payload = _build_payload(
                from_email,
                item['destinatarios'],
                f'{titulo} — {competencia} | {item["razao"]}',
                html,
                item.get('arquivos'),
            )
            if not _brevo_post(api_key, payload):
                log.error(f'Falha Brevo lote para {item["destinatarios"]}')

    for batch in batches:
        if batch:
            _pool.submit(_batch_task, batch)


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html).strip()
