from app.extensions import db
from datetime import datetime

ACOES_LABELS = {
    'aberto':        'Chamado aberto',
    'pego':          'Chamado assumido',
    'devolvido':     'Chamado devolvido',
    'finalizado':    'Chamado finalizado',
    'anexo_enviado': 'Arquivo enviado',
}


class HistoricoChamado(db.Model):
    __tablename__ = 'historico_chamados'

    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    usuario_nome = db.Column(db.String(100), nullable=False)
    acao = db.Column(db.String(30), nullable=False)
    detalhe = db.Column(db.String(300))
    criado_em = db.Column(db.DateTime, default=datetime.now)

    chamado = db.relationship('Chamado', backref='historico')

    @property
    def acao_label(self):
        return ACOES_LABELS.get(self.acao, self.acao)

    @property
    def data_formatada(self):
        meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
                 'jul', 'ago', 'set', 'out', 'nov', 'dez']
        d = self.criado_em
        return f'{d.day:02d} {meses[d.month-1]}, {d.hour:02d}:{d.minute:02d}'
