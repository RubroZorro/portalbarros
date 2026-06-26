from app.extensions import db
from datetime import datetime


class Empresa(db.Model):
    __tablename__ = 'empresas'

    id = db.Column(db.Integer, primary_key=True)
    cnpj = db.Column(db.String(20), unique=True, nullable=False)
    razao_social = db.Column(db.String(200), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    usuarios = db.relationship('Usuario', backref='empresa', lazy='select',
                                foreign_keys='Usuario.empresa_id')
    chamados = db.relationship('Chamado', backref='empresa', lazy='dynamic')
    emails   = db.relationship('EmailEmpresa', backref='empresa', lazy='select',
                                order_by='EmailEmpresa.created_at',
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Empresa {self.cnpj}>'
