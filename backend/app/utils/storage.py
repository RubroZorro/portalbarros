"""
Abstração de armazenamento de arquivos.
Em dev: salva no disco local (UPLOAD_FOLDER).
Em prod: usa Cloudflare R2 (variáveis R2_* definidas).
"""
import os
from flask import current_app, send_file, redirect


def _use_r2() -> bool:
    return bool(current_app.config.get('R2_BUCKET'))


def _client():
    import boto3
    return boto3.client(
        's3',
        endpoint_url=current_app.config['R2_ENDPOINT'],
        aws_access_key_id=current_app.config['R2_ACCESS_KEY'],
        aws_secret_access_key=current_app.config['R2_SECRET_KEY'],
        region_name='auto',
    )


def save(data: bytes, key: str) -> str:
    """Salva bytes no storage e retorna a chave."""
    if _use_r2():
        _client().put_object(
            Bucket=current_app.config['R2_BUCKET'],
            Key=key,
            Body=data,
        )
    else:
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
    return key


def delete(key: str) -> None:
    """Remove arquivo do storage. Erros são ignorados para não bloquear o fluxo."""
    try:
        if _use_r2():
            _client().delete_object(
                Bucket=current_app.config['R2_BUCKET'],
                Key=key,
            )
        else:
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], key)
            if os.path.exists(path):
                os.remove(path)
    except Exception as e:
        current_app.logger.warning(f'storage.delete falhou para {key!r}: {e}')


def serve(key: str, filename: str):
    """
    Retorna resposta Flask para download de um arquivo.
    Em prod: redireciona para URL assinada (expira em 5 min).
    Em dev: usa send_file local.
    Retorna None se o arquivo não existir (apenas em dev).
    """
    if _use_r2():
        url = _client().generate_presigned_url(
            'get_object',
            Params={'Bucket': current_app.config['R2_BUCKET'], 'Key': key},
            ExpiresIn=300,
        )
        return redirect(url)
    else:
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], key)
        if not os.path.exists(path):
            return None
        return send_file(path, download_name=filename, as_attachment=True)
