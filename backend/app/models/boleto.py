from app.extensions import db
from datetime import datetime

TAMANHO_MAXIMO = 10 * 1024 * 1024  # 10 MB

MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
         'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']


class Boleto(db.Model):
    __tablename__ = 'boletos'

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    competencia_mes = db.Column(db.Integer, nullable=False)
    competencia_ano = db.Column(db.Integer, nullable=False)
    nome_original = db.Column(db.String(255), nullable=False)
    caminho_arquivo = db.Column(db.String(500), nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    enviado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    enviado_em = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='pendente')  # pendente | recebido
    recebido_em = db.Column(db.DateTime, nullable=True)

    empresa = db.relationship('Empresa', backref='boletos')
    enviado_por = db.relationship('Usuario', backref='boletos_enviados')

    @property
    def competencia_label(self):
        return f'{MESES[self.competencia_mes - 1]} {self.competencia_ano}'

    @property
    def competencia_sort_key(self):
        return self.competencia_ano * 100 + self.competencia_mes

    @property
    def tamanho_str(self):
        kb = self.tamanho_bytes / 1024
        if kb >= 1024:
            return f'{kb / 1024:.1f} MB'
        return f'{kb:.0f} KB'
