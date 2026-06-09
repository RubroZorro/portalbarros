from app.extensions import db
from datetime import datetime
import os

TIPOS_PERMITIDOS = {'.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg', '.zip'}
TAMANHO_MAXIMO = 10 * 1024 * 1024  # 10 MB


class AnexoChamado(db.Model):
    __tablename__ = 'anexos_chamado'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False)
    nome_original = db.Column(db.String(255), nullable=False)
    caminho_arquivo = db.Column(db.String(500), nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    enviado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    enviado_em = db.Column(db.DateTime, default=datetime.now)

    enviado_por = db.relationship('Usuario', backref='anexos_enviados')
    chamado = db.relationship('Chamado', backref='anexos')

    @property
    def tamanho_str(self):
        kb = self.tamanho_bytes / 1024
        if kb >= 1024:
            return f'{kb/1024:.1f} MB'
        return f'{kb:.0f} KB'

    @property
    def extensao(self):
        return os.path.splitext(self.nome_original)[1].lower()

    @property
    def icone(self):
        ext = self.extensao
        if ext == '.pdf':
            return 'pdf'
        elif ext in ('.png', '.jpg', '.jpeg'):
            return 'img'
        elif ext in ('.docx',):
            return 'doc'
        elif ext in ('.xlsx',):
            return 'xls'
        elif ext == '.zip':
            return 'zip'
        return 'file'
