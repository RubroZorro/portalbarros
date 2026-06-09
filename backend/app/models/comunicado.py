from app.extensions import db
from datetime import datetime


class Comunicado(db.Model):
    __tablename__ = 'comunicados'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    arquivo_url = db.Column(db.String(500))
    para_todos = db.Column(db.Boolean, default=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    leituras = db.relationship('ComunicadoLeitura', backref='comunicado', lazy='dynamic')
    empresa_destino = db.relationship('Empresa', backref='comunicados_recebidos',
                                      foreign_keys=[empresa_id])

    @property
    def data_formatada(self) -> str:
        meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
                 'jul', 'ago', 'set', 'out', 'nov', 'dez']
        d = self.created_at
        return f'{d.day:02d} {meses[d.month - 1]} {d.year}'

    def __repr__(self):
        return f'<Comunicado {self.id}: {self.titulo[:40]}>'


class ComunicadoLeitura(db.Model):
    __tablename__ = 'comunicado_leituras'

    id = db.Column(db.Integer, primary_key=True)
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicados.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    lido_em = db.Column(db.DateTime, default=datetime.now)
