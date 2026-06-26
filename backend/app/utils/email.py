from flask import current_app
from flask_mail import Message
from app.extensions import mail


def send_email(destinatarios: list[str], assunto: str, corpo_html: str, corpo_texto: str = '') -> bool:
    """Envia email via Gmail SMTP. Retorna True se enviou, False se email não configurado."""
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning('MAIL_USERNAME não configurado — email não enviado.')
        return False

    try:
        msg = Message(
            subject=assunto,
            recipients=destinatarios,
            html=corpo_html,
            body=corpo_texto or _strip_html(corpo_html),
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erro ao enviar email para {destinatarios}: {e}')
        return False


def _strip_html(html: str) -> str:
    import re
    return re.sub(r'<[^>]+>', '', html).strip()
