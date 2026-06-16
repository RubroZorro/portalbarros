import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from app.models.chamado import Chamado
from app.models.comunicado import Comunicado, ComunicadoLeitura
from app.models.anexo_chamado import AnexoChamado
from app.extensions import db
from app.utils import storage
from datetime import datetime
from functools import wraps

cliente_bp = Blueprint('area_cliente', __name__)


def cliente_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'cliente':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _comunicados_da_empresa():
    return Comunicado.query.filter(
        db.or_(
            Comunicado.empresa_id.is_(None),
            Comunicado.empresa_id == current_user.empresa_id
        )
    )


@cliente_bp.route('/')
@cliente_bp.route('/inicio')
@cliente_required
def inicio():
    abertos = Chamado.query.filter_by(empresa_id=current_user.empresa_id).filter(
        Chamado.status.in_(['pendente', 'devolvido', 'em_realizacao'])
    ).count()

    lidas_ids = db.session.query(ComunicadoLeitura.comunicado_id).filter_by(
        usuario_id=current_user.id
    ).subquery()
    nao_lidos = _comunicados_da_empresa().filter(~Comunicado.id.in_(lidas_ids)).count()

    now = datetime.now()
    finalizados_mes = Chamado.query.filter_by(
        empresa_id=current_user.empresa_id, status='finalizado'
    ).filter(
        db.extract('month', Chamado.finalizado_em) == now.month,
        db.extract('year',  Chamado.finalizado_em) == now.year,
    ).count()

    comunicados = _comunicados_da_empresa().order_by(
        Comunicado.created_at.desc()
    ).limit(4).all()
    lidas_set = {r.comunicado_id for r in ComunicadoLeitura.query.filter_by(
        usuario_id=current_user.id).all()}
    chamados = Chamado.query.filter_by(
        empresa_id=current_user.empresa_id
    ).order_by(Chamado.created_at.desc()).limit(3).all()

    return render_template('area_cliente/inicio.html',
        active='inicio',
        chamados_abertos=abertos,
        nao_lidos=nao_lidos,
        finalizados_mes=finalizados_mes,
        comunicados=comunicados,
        lidas_set=lidas_set,
        chamados=chamados,
    )


@cliente_bp.route('/comunicados')
@cliente_required
def comunicados():
    todos = _comunicados_da_empresa().order_by(Comunicado.created_at.desc()).all()
    lidas_set = {r.comunicado_id for r in ComunicadoLeitura.query.filter_by(
        usuario_id=current_user.id).all()}
    return render_template('area_cliente/comunicados.html',
        active='comunicados',
        comunicados=todos,
        lidas_set=lidas_set,
    )


@cliente_bp.route('/comunicados/<int:id>/ler', methods=['POST'])
@cliente_required
def marcar_lido(id):
    existe = ComunicadoLeitura.query.filter_by(
        comunicado_id=id, usuario_id=current_user.id).first()
    if not existe:
        db.session.add(ComunicadoLeitura(
            comunicado_id=id,
            usuario_id=current_user.id,
            empresa_id=current_user.empresa_id,
        ))
        db.session.commit()
    return redirect(url_for('area_cliente.comunicados'))


@cliente_bp.route('/chamados')
@cliente_required
def meus_chamados():
    chamados = Chamado.query.filter_by(
        empresa_id=current_user.empresa_id
    ).order_by(Chamado.created_at.desc()).all()
    return render_template('area_cliente/meus_chamados.html',
        active='meus_chamados',
        chamados=chamados,
    )


@cliente_bp.route('/chamados/<int:id>')
@cliente_required
def chamado_detalhe(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.empresa_id != current_user.empresa_id:
        abort(403)
    return render_template('area_cliente/chamado_detalhe.html',
        active='meus_chamados',
        chamado=chamado,
    )


@cliente_bp.route('/chamados/<int:chamado_id>/anexos/<int:anexo_id>/download')
@cliente_required
def download_anexo(chamado_id, anexo_id):
    chamado = Chamado.query.get_or_404(chamado_id)
    if chamado.empresa_id != current_user.empresa_id:
        abort(403)
    if chamado.status != 'finalizado':
        flash('Os documentos ficam disponíveis após a conclusão do chamado.', 'erro')
        return redirect(url_for('area_cliente.chamado_detalhe', id=chamado_id))

    anexo = AnexoChamado.query.get_or_404(anexo_id)
    if anexo.chamado_id != chamado_id:
        abort(404)
    resp = storage.serve(anexo.caminho_arquivo, anexo.nome_original)
    if resp is None:
        flash('Arquivo não encontrado no servidor.', 'erro')
        return redirect(url_for('area_cliente.chamado_detalhe', id=chamado_id))
    return resp


@cliente_bp.route('/boletos')
@cliente_required
def boletos():
    from app.models.boleto import Boleto
    from itertools import groupby
    lista = Boleto.query.filter_by(
        empresa_id=current_user.empresa_id
    ).order_by(Boleto.competencia_ano.desc(), Boleto.competencia_mes.desc()).all()
    grupos = {}
    for b in lista:
        chave = (b.competencia_ano, b.competencia_mes, b.competencia_label)
        grupos.setdefault(chave, []).append(b)
    return render_template('area_cliente/boletos.html',
        active='boletos',
        grupos=grupos,
    )


@cliente_bp.route('/boletos/<int:id>/download')
@cliente_required
def download_boleto(id):
    from app.models.boleto import Boleto
    boleto = Boleto.query.get_or_404(id)
    if boleto.empresa_id != current_user.empresa_id:
        abort(403)
    if boleto.status == 'pendente':
        boleto.status = 'recebido'
        boleto.recebido_em = datetime.now()
        db.session.commit()
    resp = storage.serve(boleto.caminho_arquivo, boleto.nome_original)
    if resp is None:
        flash('Arquivo não encontrado no servidor.', 'erro')
        return redirect(url_for('area_cliente.boletos'))
    return resp


@cliente_bp.route('/recibos')
@cliente_required
def recibos():
    from app.models.recibo import Recibo
    lista = Recibo.query.filter_by(
        empresa_id=current_user.empresa_id
    ).order_by(Recibo.competencia_ano.desc(), Recibo.competencia_mes.desc()).all()
    grupos = {}
    for r in lista:
        chave = (r.competencia_ano, r.competencia_mes, r.competencia_label)
        grupos.setdefault(chave, []).append(r)
    return render_template('area_cliente/recibos.html',
        active='recibos',
        grupos=grupos,
    )


@cliente_bp.route('/recibos/<int:id>/download')
@cliente_required
def download_recibo(id):
    from app.models.recibo import Recibo
    recibo = Recibo.query.get_or_404(id)
    if recibo.empresa_id != current_user.empresa_id:
        abort(403)
    if recibo.status == 'pendente':
        recibo.status = 'recebido'
        recibo.recebido_em = datetime.now()
        db.session.commit()
    resp = storage.serve(recibo.caminho_arquivo, recibo.nome_original)
    if resp is None:
        flash('Arquivo não encontrado no servidor.', 'erro')
        return redirect(url_for('area_cliente.recibos'))
    return resp


@cliente_bp.route('/chamados/abrir', methods=['GET', 'POST'])
@cliente_required
def abrir_chamado():
    if request.method == 'POST':
        from app.utils.historico import registrar as reg_historico
        from app.utils.prazo import calcular_prazo

        tipo = request.form.get('tipo', '').strip()
        descricao = request.form.get('descricao', '').strip() or None
        nome_funcionario = None
        tipo_certidao = None

        if tipo == 'rescisao':
            nome_funcionario = request.form.get('nome_funcionario', '').strip()
            if not nome_funcionario:
                flash('Informe o nome do funcionário para o cálculo de rescisão.', 'erro')
                return redirect(url_for('area_cliente.abrir_chamado'))
            titulo = f'Cálculo de Rescisão — {nome_funcionario}'

        elif tipo == 'certidao':
            tipo_certidao = request.form.get('tipo_certidao', '').strip().upper()
            if tipo_certidao not in ('A', 'B', 'C'):
                flash('Selecione o tipo de certidão (A, B ou C).', 'erro')
                return redirect(url_for('area_cliente.abrir_chamado'))
            titulo = f'Solicitação de Certidão {tipo_certidao}'

        elif tipo == 'notas_fiscais':
            titulo = 'Envio de Notas Fiscais'

        else:
            flash('Selecione o tipo de solicitação.', 'erro')
            return redirect(url_for('area_cliente.abrir_chamado'))

        agora = datetime.now()
        chamado = Chamado(
            numero='TEMP',
            tipo=tipo,
            titulo=titulo,
            descricao=descricao,
            nome_funcionario=nome_funcionario,
            tipo_certidao=tipo_certidao,
            status='pendente',
            prazo_limite=calcular_prazo(tipo, agora),
            empresa_id=current_user.empresa_id,
            usuario_id=current_user.id,
        )
        db.session.add(chamado)
        db.session.flush()
        chamado.numero = f'#{chamado.id:04d}'
        reg_historico(chamado.id, current_user, 'aberto')
        db.session.commit()

        flash(f'Chamado {chamado.numero} aberto com sucesso!', 'sucesso')
        return redirect(url_for('area_cliente.meus_chamados'))

    return render_template('area_cliente/abrir_chamado.html', active='abrir_chamado')
