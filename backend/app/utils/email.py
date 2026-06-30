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
                   assunto: str, corpo_html: str, corpo_text: str,
                   anexos: list[tuple] | None) -> dict:
    payload = {
        'sender': {'name': 'Portal Barros & Barros', 'email': from_email},
        'to': [{'email': e} for e in destinatarios],
        'subject': assunto,
        'htmlContent': corpo_html,
        'textContent': corpo_text or ' ',
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
# API pública
# ──────────────────────────────────────────────

def send_email(
    destinatarios: list[str],
    assunto: str,
    corpo_html: str,
    anexos: list[tuple] | None = None,
) -> bool:
    """
    Agenda envio de um email via SendGrid em segundo plano.
    Retorna True se credenciais configuradas, False caso contrário.
    """
    api_key   = current_app.config.get('BREVO_API_KEY')
    from_email = current_app.config.get('MAIL_USERNAME', 'barroscontabil@gmail.com')
    if not api_key:
        current_app.logger.warning('BREVO_API_KEY não configurada — email não enviado.')
        return False

    corpo_text = _strip_html(corpo_html)
    payload = _build_payload(from_email, destinatarios, assunto, corpo_html, corpo_text, anexos)

    def _task():
        ok = _brevo_post(api_key, payload)
        if not ok:
            log.error(f'Falha SendGrid para {destinatarios} | assunto: {assunto}')

    _pool.submit(_task)
    return True


def send_emails_lote(
    lote: list[dict],
    username: str,
    password: str,
) -> None:
    """
    Envia lote de emails via SendGrid em 2 threads paralelas.
    Cada item: {destinatarios, assunto, corpo_html, anexos}.
    Não bloqueia o request.
    """
    if not lote:
        return

    # api_key vem de username (reutilizamos a assinatura; password ignorado)
    # Na prática chamamos com current_app.config direto
    from flask import current_app as _app
    api_key    = _app.config.get('BREVO_API_KEY', '')
    from_email = _app.config.get('MAIL_USERNAME', 'barroscontabil@gmail.com')

    if not api_key:
        log.warning('BREVO_API_KEY não configurada — lote não enviado.')
        return

    # Divide em 2 metades para as 2 threads do pool
    mid = (len(lote) + 1) // 2
    batches = [lote[:mid], lote[mid:]]

    def _batch_task(batch):
        for item in batch:
            corpo_text = _strip_html(item['corpo_html'])
            payload = _build_payload(
                from_email,
                item['destinatarios'],
                item['assunto'],
                item['corpo_html'],
                corpo_text,
                item.get('anexos'),
            )
            ok = _brevo_post(api_key, payload)
            if not ok:
                log.error(f'Falha SendGrid lote para {item["destinatarios"]}')

    for batch in batches:
        if batch:
            _pool.submit(_batch_task, batch)


# ──────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────

def email_cabecalho(titulo: str, competencia: str) -> str:
    return (
        '<div style="background:linear-gradient(135deg,#1B2D6B 0%,#243d8f 100%);'
        'border-radius:10px;padding:28px 24px;margin-bottom:28px;">'
        '<div style="font-size:0.6rem;font-weight:700;letter-spacing:0.2em;'
        'text-transform:uppercase;color:#C9A227;margin-bottom:10px;">'
        'Barros &amp; Barros Contabilidade</div>'
        f'<div style="color:#ffffff;font-size:1.25rem;font-weight:700;line-height:1.25;">{titulo}</div>'
        f'<div style="color:rgba(255,255,255,0.6);font-size:0.8rem;margin-top:6px;">{competencia}</div>'
        '</div>'
    )


def email_html(corpo: str) -> str:
    return f"""
<div style="font-family:'DM Sans',Arial,sans-serif;max-width:560px;margin:0 auto;color:#1a2340;">
  {corpo}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
    <span style="font-family:Georgia,serif;font-size:2rem;font-weight:700;letter-spacing:-1px;">
      <span style="color:#C9A227;">B</span><span style="color:#1B2D6B;">B</span>
    </span>
    <div style="border-left:1px solid #e5e7eb;padding-left:12px;">
      <div style="font-size:0.8rem;font-weight:700;color:#1B2D6B;text-transform:uppercase;letter-spacing:0.05em;">Barros &amp; Barros</div>
      <div style="font-size:0.65rem;color:#C9A227;text-transform:uppercase;letter-spacing:0.15em;">Contabilidade</div>
    </div>
  </div>
  <p style="font-size:0.72rem;color:#6b7280;margin:0;">
    Este é um email automático enviado pelo Portal Barros &amp; Barros.<br>
    Em caso de dúvidas, entre em contato pelo WhatsApp: (81) 99687-6093
  </p>
</div>"""


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html).strip()
