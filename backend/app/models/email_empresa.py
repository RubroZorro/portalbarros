from app.extensions import db
from datetime import datetime


class EmailEmpresa(db.Model):
    __tablename__ = 'emails_empresa'

    id         = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    email      = db.Column(db.String(200), nullable=False)
    nome_contato = db.Column(db.String(100))   # etiqueta opcional, ex: "Financeiro"
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<EmailEmpresa {self.email}>'
