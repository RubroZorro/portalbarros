from app.extensions import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='cliente')  # cliente | operador | admin
    cpf = db.Column(db.String(20), unique=True, nullable=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    senha_temporaria = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    chamados_abertos = db.relationship(
        'Chamado', backref='solicitante', lazy='dynamic', foreign_keys='Chamado.usuario_id'
    )
    chamados_atribuidos = db.relationship(
        'Chamado', backref='responsavel', lazy='dynamic', foreign_keys='Chamado.atribuido_a'
    )

    def set_password(self, senha: str):
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def inicial(self) -> str:
        return self.nome[0].upper() if self.nome else '?'

    def __repr__(self):
        return f'<Usuario {self.email} [{self.role}]>'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))
