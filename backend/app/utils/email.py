import logging
import re
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email import encoders as email_encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

# Pool compartilhado: no máximo 2 conexões SMTP simultâneas
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='smtp')

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────

def _build_msg(username, destinatarios, assunto, corpo_html, corpo_text, anexos):
    msg = MIMEMultipart('mixed')
    msg['From'] = f'Portal Barros & Barros <{username}>'
    msg['To'] = ', '.join(destinatarios)
    msg['Subject'] = assunto
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(corpo_text, 'plain', 'utf-8'))
    alt.attach(MIMEText(corpo_html, 'html', 'utf-8'))
    msg.attach(alt)
    for filename, data, content_type in (anexos or []):
        mime_type, mime_sub = content_type.split('/', 1)
        part = MIMEBase(mime_type, mime_sub)
        part.set_payload(data)
        email_encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(part)
    return msg


def _smtp_connect(username, password):
    server = smtplib.SMTP('smtp.gmail.com', 587, timeout=20)
    server.ehlo()
    server.starttls()
    server.login(username, password)
    return server


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
    Agenda envio de um email em segundo plano (não bloqueia o request).
    Retorna True se credenciais configuradas, False caso contrário.
    """
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    if not username or not password:
        current_app.logger.warning('MAIL_USERNAME/PASSWORD não configurado.')
        return False

    corpo_text = _strip_html(corpo_html)

    def _task():
        try:
            with _smtp_connect(username, password) as server:
                msg = _build_msg(username, destinatarios, assunto, corpo_html, corpo_text, anexos)
                server.sendmail(username, destinatarios, msg.as_bytes())
        except Exception as e:
            log.error(f'Erro SMTP para {destinatarios}: {e}')

    _pool.submit(_task)
    return True


def send_emails_lote(
    lote: list[dict],
    username: str,
    password: str,
) -> None:
    """
    Envia múltiplos emails em uma única conexão SMTP (eficiente para lote).
    Cada item do lote: {destinatarios, assunto, corpo_html, anexos}.
    Roda em thread separada — não bloqueia o request.
    """
    if not lote:
        return

    def _task():
        try:
            with _smtp_connect(username, password) as server:
                for item in lote:
                    try:
                        corpo_text = _strip_html(item['corpo_html'])
                        msg = _build_msg(
                            username,
                            item['destinatarios'],
                            item['assunto'],
                            item['corpo_html'],
                            corpo_text,
                            item.get('anexos'),
                        )
                        server.sendmail(username, item['destinatarios'], msg.as_bytes())
                    except Exception as e:
                        log.error(f'Erro ao enviar lote para {item["destinatarios"]}: {e}')
        except Exception as e:
            log.error(f'Erro conexão SMTP no lote: {e}')

    _pool.submit(_task)


# ──────────────────────────────────────────────
# Templates de email
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
