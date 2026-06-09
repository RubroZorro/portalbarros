import os
import uuid
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, current_app, abort, send_file)
from flask_login import login_required, current_user
from functools import wraps
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.chamado import Chamado
from app.models.comunicado import Comunicado, ComunicadoLeitura
from app.models.anexo_chamado import AnexoChamado, TIPOS_PERMITIDOS, TAMANHO_MAXIMO
from app.models.historico_chamado import HistoricoChamado
from app.models.empresa import Empresa
from app.utils.historico import registrar as reg_historico

colab_bp = Blueprint('area_colab', __name__)


def colab_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role not in ('operador', 'admin'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _empresas_clientes():
    from app.models.usuario import Usuario
    from sqlalchemy import exists
    return Empresa.query.filter(
        Empresa.ativo == True,
        exists().where((Usuario.empresa_id == Empresa.id) & (Usuario.role == 'cliente'))
    ).order_by(Empresa.razao_social).all()


# ── DASHBOARD (kanban) ──────────────────────────────────────────────────────

@colab_bp.route('/')
@colab_bp.route('/dashboard')
@colab_required
def dashboard():
    # Filtros para coluna Finalizado
    f_empresa = request.args.get('empresa_id', type=int)
    f_tipo    = request.args.get('tipo', '')
    f_colab   = request.args.get('colaborador', '')
    f_de      = request.args.get('de', '')
    f_ate     = request.args.get('ate', '')

    em_aberto = Chamado.query.filter(
        Chamado.status.in_(['pendente', 'devolvido']),
        Chamado.atribuido_a.is_(None)
    ).order_by(Chamado.created_at.asc()).all()

    realizando = Chamado.query.filter_by(
        status='em_realizacao'
    ).order_by(Chamado.atribuido_em.asc()).all()

    q = Chamado.query.filter_by(status='finalizado')
    if f_empresa:
        q = q.filter_by(empresa_id=f_empresa)
    if f_tipo:
        q = q.filter_by(tipo=f_tipo)
    if f_colab:
        q = q.filter(Chamado.finalizado_por_nome.ilike(f'%{f_colab}%'))
    if f_de:
        try:
            q = q.filter(Chamado.finalizado_em >= datetime.strptime(f_de, '%Y-%m-%d'))
        except ValueError:
            pass
    if f_ate:
        try:
            from datetime import timedelta
            q = q.filter(Chamado.finalizado_em <= datetime.strptime(f_ate, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass
    finalizado = q.order_by(Chamado.finalizado_em.desc()).all()

    return render_template('area_colab/dashboard.html',
        active='chamados',
        em_aberto=em_aberto,
        realizando=realizando,
        finalizado=finalizado,
        empresas_filtro=_empresas_clientes(),
        f_empresa=f_empresa, f_tipo=f_tipo, f_colab=f_colab, f_de=f_de, f_ate=f_ate,
    )


# ── AÇÕES DE STATUS ─────────────────────────────────────────────────────────

@colab_bp.route('/chamados/<int:id>/pegar', methods=['POST'])
@colab_required
def pegar_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.status not in ('pendente', 'devolvido') or chamado.atribuido_a:
        flash('Este chamado não está mais disponível.', 'erro')
        return redirect(url_for('area_colab.dashboard'))

    chamado.status = 'em_realizacao'
    chamado.atribuido_a = current_user.id
    chamado.atribuido_em = datetime.now()
    chamado.devolvido_por_nome = None

    reg_historico(chamado.id, current_user, 'pego')
    db.session.commit()

    flash(f'Chamado {chamado.numero} assumido com sucesso.', 'sucesso')
    return redirect(url_for('area_colab.chamado_detalhe', id=id))


@colab_bp.route('/chamados/<int:id>/devolver', methods=['POST'])
@colab_required
def devolver_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.atribuido_a != current_user.id and current_user.role != 'admin':
        abort(403)

    motivo = request.form.get('motivo', '').strip()
    chamado.status = 'devolvido'
    chamado.devolvido_por_nome = current_user.nome
    chamado.atribuido_a = None
    chamado.atribuido_em = None

    reg_historico(chamado.id, current_user, 'devolvido',
                  f'Motivo: {motivo}' if motivo else None)
    db.session.commit()

    flash(f'Chamado {chamado.numero} devolvido.', 'sucesso')
    return redirect(url_for('area_colab.dashboard'))


@colab_bp.route('/chamados/<int:id>/finalizar', methods=['POST'])
@colab_required
def finalizar_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.atribuido_a != current_user.id and current_user.role != 'admin':
        abort(403)

    agora = datetime.now()
    chamado.status = 'finalizado'
    chamado.finalizado_por_nome = current_user.nome
    chamado.finalizado_em = agora

    reg_historico(chamado.id, current_user, 'finalizado')

    # Comunicado automático para o cliente
    n_anexos = len(chamado.anexos)
    extra = f' {n_anexos} documento(s) disponível(is) para download em "Meus Chamados".' if n_anexos else ''
    db.session.add(Comunicado(
        titulo=f'Chamado {chamado.numero} finalizado',
        conteudo=(f'Sua solicitação "{chamado.titulo}" foi concluída pela nossa equipe.{extra}'
                  ' Em caso de dúvidas, abra um novo chamado.'),
        empresa_id=chamado.empresa_id,
        para_todos=False,
    ))
    db.session.commit()

    flash(f'Chamado {chamado.numero} finalizado. O cliente foi notificado.', 'sucesso')
    return redirect(url_for('area_colab.dashboard'))


# ── DETALHE DO CHAMADO ──────────────────────────────────────────────────────

@colab_bp.route('/chamados/<int:id>')
@colab_required
def chamado_detalhe(id):
    chamado = Chamado.query.get_or_404(id)
    historico = HistoricoChamado.query.filter_by(
        chamado_id=id
    ).order_by(HistoricoChamado.criado_em.desc()).all()
    return render_template('area_colab/chamado_detalhe.html',
        active='chamados',
        chamado=chamado,
        historico=historico,
    )


# ── ANEXOS ──────────────────────────────────────────────────────────────────

@colab_bp.route('/chamados/<int:id>/anexos', methods=['POST'])
@colab_required
def upload_anexo(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.atribuido_a != current_user.id and current_user.role != 'admin':
        flash('Você precisa ter assumido o chamado para enviar documentos.', 'erro')
        return redirect(url_for('area_colab.chamado_detalhe', id=id))
    arquivo = request.files.get('arquivo')

    if not arquivo or not arquivo.filename:
        flash('Nenhum arquivo selecionado.', 'erro')
        return redirect(url_for('area_colab.chamado_detalhe', id=id))

    nome_original = arquivo.filename
    ext = os.path.splitext(secure_filename(nome_original))[1].lower()

    if ext not in TIPOS_PERMITIDOS:
        flash(f'Tipo não permitido. Use: pdf, docx, xlsx, png, jpg, zip.', 'erro')
        return redirect(url_for('area_colab.chamado_detalhe', id=id))

    arquivo.seek(0, 2)
    tamanho = arquivo.tell()
    arquivo.seek(0)
    if tamanho > TAMANHO_MAXIMO:
        flash('Arquivo muito grande. Máximo: 10 MB.', 'erro')
        return redirect(url_for('area_colab.chamado_detalhe', id=id))

    pasta = os.path.join(current_app.config['UPLOAD_FOLDER'], str(chamado.id))
    os.makedirs(pasta, exist_ok=True)
    nome_salvo = f'{uuid.uuid4().hex}{ext}'
    caminho = os.path.join(pasta, nome_salvo)
    arquivo.save(caminho)

    db.session.add(AnexoChamado(
        chamado_id=chamado.id,
        nome_original=nome_original,
        caminho_arquivo=caminho,
        tamanho_bytes=tamanho,
        enviado_por_id=current_user.id,
    ))
    reg_historico(chamado.id, current_user, 'anexo_enviado', f'Arquivo: {nome_original}')
    db.session.commit()

    flash(f'"{nome_original}" enviado com sucesso.', 'sucesso')
    return redirect(url_for('area_colab.chamado_detalhe', id=id))


@colab_bp.route('/chamados/<int:chamado_id>/anexos/<int:anexo_id>/download')
@colab_required
def download_anexo(chamado_id, anexo_id):
    anexo = AnexoChamado.query.get_or_404(anexo_id)
    if anexo.chamado_id != chamado_id:
        abort(404)
    if not os.path.exists(anexo.caminho_arquivo):
        flash('Arquivo não encontrado no servidor.', 'erro')
        return redirect(url_for('area_colab.chamado_detalhe', id=chamado_id))
    return send_file(anexo.caminho_arquivo,
                     download_name=anexo.nome_original,
                     as_attachment=True)


# ── COMUNICADOS ─────────────────────────────────────────────────────────────

@colab_bp.route('/comunicados')
@colab_required
def comunicados():
    from sqlalchemy import func, exists
    from app.models.usuario import Usuario

    todos = Comunicado.query.order_by(Comunicado.created_at.desc()).all()

    total_clientes = db.session.query(func.count(Empresa.id)).filter(
        Empresa.ativo == True,
        exists().where(
            (Usuario.empresa_id == Empresa.id) & (Usuario.role == 'cliente')
        )
    ).scalar() or 0

    stats = {}
    for c in todos:
        leram = db.session.query(
            func.count(func.distinct(ComunicadoLeitura.empresa_id))
        ).filter_by(comunicado_id=c.id).scalar() or 0
        total = total_clientes if c.empresa_id is None else 1
        stats[c.id] = {'leram': leram, 'total': total}

    return render_template('area_colab/comunicados.html',
        active='comunicados',
        comunicados=todos,
        stats=stats,
    )


@colab_bp.route('/comunicados/criar', methods=['GET', 'POST'])
@colab_required
def criar_comunicado():
    empresas = _empresas_clientes()

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        conteudo = request.form.get('conteudo', '').strip()
        dest = request.form.get('destinatario', 'todos')
        empresa_id_val = request.form.get('empresa_id', type=int)

        if not titulo or not conteudo:
            flash('Título e mensagem são obrigatórios.', 'erro')
            return render_template('area_colab/criar_comunicado.html',
                                   active='criar_comunicado', empresas=empresas)

        if dest == 'especifico' and not empresa_id_val:
            flash('Selecione a empresa destinatária.', 'erro')
            return render_template('area_colab/criar_comunicado.html',
                                   active='criar_comunicado', empresas=empresas)

        db.session.add(Comunicado(
            titulo=titulo,
            conteudo=conteudo,
            para_todos=(dest == 'todos'),
            empresa_id=empresa_id_val if dest == 'especifico' else None,
        ))
        db.session.commit()

        flash('Comunicado enviado com sucesso.', 'sucesso')
        return redirect(url_for('area_colab.comunicados'))

    return render_template('area_colab/criar_comunicado.html',
                           active='criar_comunicado', empresas=empresas)


# Compatibilidade: rota legada usada pelo admin dashboard
@colab_bp.route('/chamados/<int:id>/status', methods=['POST'])
@colab_required
def atualizar_status(id):
    chamado = Chamado.query.get_or_404(id)
    novo = request.form.get('status')
    if novo in ('pendente', 'em_realizacao', 'finalizado'):
        chamado.status = novo
        db.session.commit()
    return redirect(url_for('area_colab.dashboard'))
