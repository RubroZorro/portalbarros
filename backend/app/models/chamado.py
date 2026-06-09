from app.extensions import db
from datetime import datetime

TIPO_LABELS = {
    'rescisao':      'Rescisão',
    'certidao':      'Certidão',
    'notas_fiscais': 'Notas Fiscais',
}

# Visão do cliente
STATUS_LABELS = {
    'pendente':      'Pendente',
    'devolvido':     'Pendente',
    'em_realizacao': 'Em Atendimento',
    'finalizado':    'Finalizado',
}

STATUS_CSS = {
    'pendente':      's-pendente',
    'devolvido':     's-pendente',
    'em_realizacao': 's-recebido',
    'finalizado':    's-finalizado',
}

# Visão do colaborador
STATUS_COLAB = {
    'pendente':      'Em Aberto',
    'devolvido':     'Em Aberto',
    'em_realizacao': 'Realizando',
    'finalizado':    'Finalizado',
}


class Chamado(db.Model):
    __tablename__ = 'chamados'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(10), unique=True)
    tipo = db.Column(db.String(20), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    nome_funcionario = db.Column(db.String(100))
    tipo_certidao = db.Column(db.String(5))
    status = db.Column(db.String(20), nullable=False, default='pendente')
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    atribuido_a = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    atribuido_em = db.Column(db.DateTime)
    prazo_limite = db.Column(db.DateTime)
    devolvido_por_nome = db.Column(db.String(100))
    finalizado_por_nome = db.Column(db.String(100))
    finalizado_em = db.Column(db.DateTime)
    editado_por_nome = db.Column(db.String(100))
    editado_em = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def tipo_label(self) -> str:
        return TIPO_LABELS.get(self.tipo, self.tipo)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def status_css(self) -> str:
        return STATUS_CSS.get(self.status, '')

    @property
    def status_colab_label(self) -> str:
        return STATUS_COLAB.get(self.status, self.status)

    @property
    def semaforo(self):
        if self.status == 'finalizado' or not self.prazo_limite:
            return None
        diff_h = (self.prazo_limite - datetime.now()).total_seconds() / 3600
        if diff_h <= 0:
            return 'vermelho'
        elif diff_h <= 8:
            return 'amarelo'
        return 'verde'

    @property
    def tempo_restante_str(self) -> str:
        if not self.prazo_limite or self.status == 'finalizado':
            return ''
        diff = (self.prazo_limite - datetime.now()).total_seconds()
        if diff <= 0:
            h = int(abs(diff) / 3600)
            return f'{h}h em atraso' if h > 0 else 'Vencido'
        horas = int(diff / 3600)
        minutos = int((diff % 3600) / 60)
        if horas >= 24:
            d = horas // 24
            h = horas % 24
            return f'{d}d {h}h' if h else f'{d}d'
        return f'{horas}h {minutos}min' if horas else f'{minutos}min'

    @property
    def data_formatada(self) -> str:
        meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
                 'jul', 'ago', 'set', 'out', 'nov', 'dez']
        d = self.created_at
        return f'{d.day:02d} {meses[d.month - 1]} {d.year}'

    @property
    def prazo_formatado(self) -> str:
        if not self.prazo_limite:
            return '—'
        meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
                 'jul', 'ago', 'set', 'out', 'nov', 'dez']
        d = self.prazo_limite
        return f'{d.day:02d} {meses[d.month - 1]}, {d.hour:02d}:{d.minute:02d}'

    def __repr__(self):
        return f'<Chamado {self.numero} [{self.status}]>'
