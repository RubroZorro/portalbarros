import os
import uuid
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, current_app)
from app.utils import storage
from flask_login import login_required, current_user

from app.extensions import db
from app.models.usuario import Usuario
from app.models.empresa import Empresa
from app.models.chamado import Chamado
from app.models.historico_chamado import HistoricoChamado
from app.models.boleto import Boleto
from app.models.recibo import Recibo

admin_bp = Blueprint('area_admin', __name__)

MESES_NOMES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
               'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _gerar_senha_temp():
    chars = string.ascii_letters + string.digits
    return 'Bb@' + ''.join(secrets.choice(chars) for _ in range(6))


def _upload_financeiro(pasta):
    """Salva arquivo PDF do request; retorna (key, nome_original, tamanho) ou None."""
    arquivo = request.files.get('arquivo')
    if not arquivo or arquivo.filename == '':
        flash('Selecione um arquivo PDF.', 'erro')
        return None
    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext != '.pdf':
        flash('Apenas arquivos PDF são aceitos.', 'erro')
        return None
    dados = arquivo.read()
    if len(dados) > 10 * 1024 * 1024:
        flash('Arquivo excede o limite de 10 MB.', 'erro')
        return None
    empresa_id = request.form.get('empresa_id', '')
    key = f'{pasta}/{empresa_id}/{uuid.uuid4().hex}.pdf'
    storage.save(dados, key)
    return key, arquivo.filename, len(dados)


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    periodo = int(request.args.get('periodo', 30))
    data_inicio = datetime.now() - timedelta(days=periodo)
    agora = datetime.now()

    # ── Saúde operacional ──
    chamados_vencidos = Chamado.query.filter(
        Chamado.status != 'finalizado',
        Chamado.prazo_limite.isnot(None),
        Chamado.prazo_limite < agora
    ).order_by(Chamado.prazo_limite.asc()).all()

    sem_responsavel = Chamado.query.filter(
        Chamado.status.in_(['pendente', 'devolvido']),
        Chamado.atribuido_a.is_(None),
        Chamado.created_at < agora - timedelta(hours=24)
    ).order_by(Chamado.created_at.asc()).all()

    sem_movimentacao = Chamado.query.filter(
        Chamado.status == 'em_realizacao',
        Chamado.updated_at < agora - timedelta(days=3)
    ).order_by(Chamado.updated_at.asc()).all()

    # ── Stats gerais ──
    total_abertos = Chamado.query.filter(
        Chamado.status.in_(['pendente', 'devolvido', 'em_realizacao'])
    ).count()
    total_empresas = Empresa.query.filter_by(ativo=True).count()
    finalizados_mes = Chamado.query.filter(
        Chamado.status == 'finalizado',
        db.extract('month', Chamado.finalizado_em) == agora.month,
        db.extract('year', Chamado.finalizado_em) == agora.year,
    ).count()
    total_colaboradores = Usuario.query.filter(
        Usuario.role.in_(['operador', 'admin']),
        Usuario.ativo == True
    ).count()

    # ── Métricas por colaborador ──
    colaboradores = Usuario.query.filter(
        Usuario.role.in_(['operador', 'admin']),
        Usuario.ativo == True
    ).order_by(Usuario.nome).all()

    metricas_colab = []
    for colab in colaboradores:
        pegos = HistoricoChamado.query.filter(
            HistoricoChamado.usuario_id == colab.id,
            HistoricoChamado.acao == 'pego',
            HistoricoChamado.criado_em >= data_inicio
        ).count()
        finalizados = HistoricoChamado.query.filter(
            HistoricoChamado.usuario_id == colab.id,
            HistoricoChamado.acao == 'finalizado',
            HistoricoChamado.criado_em >= data_inicio
        ).count()
        devolvidos = HistoricoChamado.query.filter(
            HistoricoChamado.usuario_id == colab.id,
            HistoricoChamado.acao == 'devolvido',
            HistoricoChamado.criado_em >= data_inicio
        ).count()
        taxa = round(devolvidos / pegos * 100) if pegos > 0 else 0
        metricas_colab.append({
            'nome': colab.nome,
            'pegos': pegos,
            'finalizados': finalizados,
            'devolvidos': devolvidos,
            'taxa_devolucao': taxa,
        })

    return render_template('area_admin/dashboard.html',
        active='dashboard',
        periodo=periodo,
        chamados_vencidos=chamados_vencidos,
        sem_responsavel=sem_responsavel,
        sem_movimentacao=sem_movimentacao,
        total_abertos=total_abertos,
        total_empresas=total_empresas,
        finalizados_mes=finalizados_mes,
        total_colaboradores=total_colaboradores,
        metricas_colab=metricas_colab,
    )


# ──────────────────────────────────────────────
# EMPRESAS
# ──────────────────────────────────────────────

@admin_bp.route('/empresas')
@admin_required
def empresas():
    lista = Empresa.query.order_by(Empresa.razao_social).all()
    return render_template('area_admin/empresas.html', active='empresas', empresas=lista)


@admin_bp.route('/empresas/nova', methods=['GET', 'POST'])
@admin_required
def empresa_nova():
    if request.method == 'POST':
        cnpj = request.form.get('cnpj', '').strip()
        razao = request.form.get('razao_social', '').strip()
        if not cnpj or not razao:
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return redirect(url_for('area_admin.empresa_nova'))
        if Empresa.query.filter_by(cnpj=cnpj).first():
            flash('Já existe uma empresa com esse CNPJ.', 'erro')
            return redirect(url_for('area_admin.empresa_nova'))
        db.session.add(Empresa(cnpj=cnpj, razao_social=razao, ativo=True))
        db.session.commit()
        flash(f'Empresa "{razao}" criada com sucesso.', 'sucesso')
        return redirect(url_for('area_admin.empresas'))
    return render_template('area_admin/empresa_form.html', active='empresas', empresa=None)


@admin_bp.route('/empresas/<int:id>/editar', methods=['GET', 'POST'])
@admin_required
def empresa_editar(id):
    empresa = Empresa.query.get_or_404(id)
    if request.method == 'POST':
        cnpj = request.form.get('cnpj', '').strip()
        razao = request.form.get('razao_social', '').strip()
        if not cnpj or not razao:
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return redirect(url_for('area_admin.empresa_editar', id=id))
        conflito = Empresa.query.filter(Empresa.cnpj == cnpj, Empresa.id != id).first()
        if conflito:
            flash('Já existe outra empresa com esse CNPJ.', 'erro')
            return redirect(url_for('area_admin.empresa_editar', id=id))
        empresa.cnpj = cnpj
        empresa.razao_social = razao
        db.session.commit()
        flash('Empresa atualizada.', 'sucesso')
        return redirect(url_for('area_admin.empresas'))
    return render_template('area_admin/empresa_form.html', active='empresas', empresa=empresa)


@admin_bp.route('/empresas/<int:id>/toggle', methods=['POST'])
@admin_required
def empresa_toggle(id):
    empresa = Empresa.query.get_or_404(id)
    empresa.ativo = not empresa.ativo
    db.session.commit()
    estado = 'ativada' if empresa.ativo else 'desativada'
    flash(f'Empresa "{empresa.razao_social}" {estado}.', 'sucesso')
    return redirect(url_for('area_admin.empresas'))


# ──────────────────────────────────────────────
# USUÁRIOS
# ──────────────────────────────────────────────

@admin_bp.route('/usuarios')
@admin_required
def usuarios():
    empresa_filtro = request.args.get('empresa_id', type=int)
    q = Usuario.query
    if empresa_filtro:
        q = q.filter_by(empresa_id=empresa_filtro)
    lista = q.order_by(Usuario.nome).all()
    empresas_lista = Empresa.query.filter_by(ativo=True).order_by(Empresa.razao_social).all()
    return render_template('area_admin/usuarios.html',
        active='usuarios',
        usuarios=lista,
        empresas=empresas_lista,
        empresa_filtro=empresa_filtro,
    )


@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@admin_required
def usuario_novo():
    empresas_clientes = Empresa.query.filter(
        Empresa.cnpj != '00.000.000/0001-00',
        Empresa.ativo == True
    ).order_by(Empresa.razao_social).all()
    escritorio = Empresa.query.filter_by(cnpj='00.000.000/0001-00').first()

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', '').strip()

        if not nome or not email or role not in ('cliente', 'operador', 'admin'):
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return redirect(url_for('area_admin.usuario_novo'))
        if Usuario.query.filter_by(email=email).first():
            flash('Já existe um usuário com esse e-mail.', 'erro')
            return redirect(url_for('area_admin.usuario_novo'))

        cpf = request.form.get('cpf', '').strip() or None

        if role in ('operador', 'admin'):
            if not cpf:
                flash('CPF é obrigatório para operadores e administradores.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))
            if Usuario.query.filter_by(cpf=cpf).first():
                flash('Já existe um usuário com esse CPF.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))

        if role == 'cliente':
            empresa_id = request.form.get('empresa_id', type=int)
            if not empresa_id:
                flash('Selecione a empresa do cliente.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))
        else:
            empresa_id = escritorio.id if escritorio else None

        senha = _gerar_senha_temp()
        u = Usuario(nome=nome, email=email, role=role, cpf=cpf,
                    empresa_id=empresa_id, ativo=True, senha_temporaria=True)
        u.set_password(senha)
        db.session.add(u)
        db.session.commit()
        flash(f'Usuário criado. Senha temporária: {senha}', 'sucesso')
        return redirect(url_for('area_admin.usuarios'))

    return render_template('area_admin/usuario_form.html',
        active='usuarios',
        usuario=None,
        empresas=empresas_clientes,
    )


@admin_bp.route('/usuarios/<int:id>/editar', methods=['GET', 'POST'])
@admin_required
def usuario_editar(id):
    usuario = Usuario.query.get_or_404(id)
    empresas_clientes = Empresa.query.filter(
        Empresa.cnpj != '00.000.000/0001-00',
        Empresa.ativo == True
    ).order_by(Empresa.razao_social).all()

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', '').strip()

        if not nome or not email or role not in ('cliente', 'operador', 'admin'):
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return redirect(url_for('area_admin.usuario_editar', id=id))

        conflito = Usuario.query.filter(Usuario.email == email, Usuario.id != id).first()
        if conflito:
            flash('Já existe outro usuário com esse e-mail.', 'erro')
            return redirect(url_for('area_admin.usuario_editar', id=id))

        cpf = request.form.get('cpf', '').strip() or None
        escritorio = Empresa.query.filter_by(cnpj='00.000.000/0001-00').first()

        if role in ('operador', 'admin'):
            if not cpf:
                flash('CPF é obrigatório para operadores e administradores.', 'erro')
                return redirect(url_for('area_admin.usuario_editar', id=id))
            conflito_cpf = Usuario.query.filter(Usuario.cpf == cpf, Usuario.id != id).first()
            if conflito_cpf:
                flash('Já existe outro usuário com esse CPF.', 'erro')
                return redirect(url_for('area_admin.usuario_editar', id=id))

        if role == 'cliente':
            empresa_id = request.form.get('empresa_id', type=int)
            if not empresa_id:
                flash('Selecione a empresa do cliente.', 'erro')
                return redirect(url_for('area_admin.usuario_editar', id=id))
        else:
            empresa_id = escritorio.id if escritorio else usuario.empresa_id

        usuario.nome = nome
        usuario.email = email
        usuario.role = role
        usuario.cpf = cpf
        usuario.empresa_id = empresa_id
        db.session.commit()
        flash('Usuário atualizado.', 'sucesso')
        return redirect(url_for('area_admin.usuarios'))

    return render_template('area_admin/usuario_form.html',
        active='usuarios',
        usuario=usuario,
        empresas=empresas_clientes,
    )


@admin_bp.route('/usuarios/<int:id>/toggle', methods=['POST'])
@admin_required
def usuario_toggle(id):
    usuario = Usuario.query.get_or_404(id)
    if usuario.id == current_user.id:
        flash('Você não pode desativar sua própria conta.', 'erro')
        return redirect(url_for('area_admin.usuarios'))
    usuario.ativo = not usuario.ativo
    db.session.commit()
    estado = 'ativado' if usuario.ativo else 'desativado'
    flash(f'Usuário "{usuario.nome}" {estado}.', 'sucesso')
    return redirect(url_for('area_admin.usuarios'))


@admin_bp.route('/usuarios/<int:id>/reset-senha', methods=['POST'])
@admin_required
def usuario_reset_senha(id):
    usuario = Usuario.query.get_or_404(id)
    senha = _gerar_senha_temp()
    usuario.set_password(senha)
    usuario.senha_temporaria = True
    db.session.commit()
    flash(f'Senha redefinida. Nova senha temporária: {senha}', 'sucesso')
    return redirect(url_for('area_admin.usuarios'))


# ──────────────────────────────────────────────
# BOLETOS
# ──────────────────────────────────────────────

@admin_bp.route('/boletos')
@admin_required
def boletos():
    empresa_filtro = request.args.get('empresa_id', type=int)
    q = Boleto.query
    if empresa_filtro:
        q = q.filter_by(empresa_id=empresa_filtro)
    lista = q.order_by(
        Boleto.competencia_ano.desc(), Boleto.competencia_mes.desc(), Boleto.enviado_em.desc()
    ).all()
    empresas_lista = Empresa.query.filter(
        Empresa.cnpj != '00.000.000/0001-00',
        Empresa.ativo == True
    ).order_by(Empresa.razao_social).all()
    return render_template('area_admin/boletos.html',
        active='boletos',
        boletos=lista,
        empresas=empresas_lista,
        empresa_filtro=empresa_filtro,
        meses=MESES_NOMES,
        ano_atual=datetime.now().year,
    )


@admin_bp.route('/boletos/upload', methods=['POST'])
@admin_required
def boleto_upload():
    empresa_id = request.form.get('empresa_id', type=int)
    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)

    if not empresa_id or not mes or not ano:
        flash('Preencha empresa, mês e ano.', 'erro')
        return redirect(url_for('area_admin.boletos'))
    if not (1 <= mes <= 12):
        flash('Mês inválido.', 'erro')
        return redirect(url_for('area_admin.boletos'))

    resultado = _upload_financeiro('boletos')
    if resultado is None:
        return redirect(url_for('area_admin.boletos'))

    caminho, nome_original, tamanho = resultado
    db.session.add(Boleto(
        empresa_id=empresa_id,
        competencia_mes=mes,
        competencia_ano=ano,
        nome_original=nome_original,
        caminho_arquivo=caminho,
        tamanho_bytes=tamanho,
        enviado_por_id=current_user.id,
    ))
    db.session.commit()
    flash('Boleto enviado com sucesso.', 'sucesso')
    return redirect(url_for('area_admin.boletos'))


@admin_bp.route('/boletos/<int:id>/excluir', methods=['POST'])
@admin_required
def boleto_excluir(id):
    boleto = Boleto.query.get_or_404(id)
    storage.delete(boleto.caminho_arquivo)
    db.session.delete(boleto)
    db.session.commit()
    flash('Boleto excluído.', 'sucesso')
    return redirect(url_for('area_admin.boletos'))


# ──────────────────────────────────────────────
# RECIBOS
# ──────────────────────────────────────────────

@admin_bp.route('/recibos')
@admin_required
def recibos():
    empresa_filtro = request.args.get('empresa_id', type=int)
    q = Recibo.query
    if empresa_filtro:
        q = q.filter_by(empresa_id=empresa_filtro)
    lista = q.order_by(
        Recibo.competencia_ano.desc(), Recibo.competencia_mes.desc(), Recibo.enviado_em.desc()
    ).all()
    empresas_lista = Empresa.query.filter(
        Empresa.cnpj != '00.000.000/0001-00',
        Empresa.ativo == True
    ).order_by(Empresa.razao_social).all()
    return render_template('area_admin/recibos.html',
        active='recibos',
        recibos=lista,
        empresas=empresas_lista,
        empresa_filtro=empresa_filtro,
        meses=MESES_NOMES,
        ano_atual=datetime.now().year,
    )


@admin_bp.route('/recibos/upload', methods=['POST'])
@admin_required
def recibo_upload():
    empresa_id = request.form.get('empresa_id', type=int)
    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)

    if not empresa_id or not mes or not ano:
        flash('Preencha empresa, mês e ano.', 'erro')
        return redirect(url_for('area_admin.recibos'))
    if not (1 <= mes <= 12):
        flash('Mês inválido.', 'erro')
        return redirect(url_for('area_admin.recibos'))

    resultado = _upload_financeiro('recibos')
    if resultado is None:
        return redirect(url_for('area_admin.recibos'))

    caminho, nome_original, tamanho = resultado
    db.session.add(Recibo(
        empresa_id=empresa_id,
        competencia_mes=mes,
        competencia_ano=ano,
        nome_original=nome_original,
        caminho_arquivo=caminho,
        tamanho_bytes=tamanho,
        enviado_por_id=current_user.id,
    ))
    db.session.commit()
    flash('Recibo enviado com sucesso.', 'sucesso')
    return redirect(url_for('area_admin.recibos'))


@admin_bp.route('/recibos/<int:id>/excluir', methods=['POST'])
@admin_required
def recibo_excluir(id):
    recibo = Recibo.query.get_or_404(id)
    storage.delete(recibo.caminho_arquivo)
    db.session.delete(recibo)
    db.session.commit()
    flash('Recibo excluído.', 'sucesso')
    return redirect(url_for('area_admin.recibos'))
