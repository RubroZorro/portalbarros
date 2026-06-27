from flask import current_app
from flask_mail import Message
from app.extensions import mail


def send_email(
    destinatarios: list[str],
    assunto: str,
    corpo_html: str,
    anexos: list[tuple] | None = None,
) -> bool:
    """
    Envia email via Gmail SMTP.
    anexos: lista de (filename, bytes, content_type)
    Retorna True se enviou, False se email não configurado ou erro.
    """
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning('MAIL_USERNAME não configurado — email não enviado.')
        return False

    try:
        msg = Message(
            subject=assunto,
            recipients=destinatarios,
            html=corpo_html,
            body=_strip_html(corpo_html),
        )
        for filename, data, content_type in (anexos or []):
            msg.attach(filename, content_type, data)
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erro ao enviar email para {destinatarios}: {e}')
        return False


def email_html(corpo: str) -> str:
    """Envolve o corpo em template com rodapé Barros & Barros."""
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
    import re
    return re.sub(r'<[^>]+>', '', html).strip()
