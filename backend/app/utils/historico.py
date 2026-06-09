from app.extensions import db
from app.models.historico_chamado import HistoricoChamado


def registrar(chamado_id: int, usuario, acao: str, detalhe: str = ''):
    h = HistoricoChamado(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao=acao,
        detalhe=detalhe or None,
    )
    db.session.add(h)
