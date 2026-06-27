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
from app.models.comunicado import Comunicado
from app.models.documento import Documento
from app.models.email_empresa import EmailEmpresa

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
    """Salva arquivo PDF do request; retorna (key, nome_original, tamanho, dados) ou None."""
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
    return key, arquivo.filename, len(dados), dados


def _enviar_arquivo_por_email(empresa_id, mes, ano, nome_arquivo, dados, tipo, anexos=None):
    """Envia arquivo(s) por email para os contatos cadastrados da empresa."""
    from app.models.email_empresa import EmailEmpresa
    from app.utils.email import send_email, email_html

    emails = [e.email for e in EmailEmpresa.query.filter_by(empresa_id=empresa_id).all()]
    if not emails:
        return

    empresa = Empresa.query.get(empresa_id)
    mes_nome = MESES_NOMES[mes - 1]
    tipo_label = {'boleto': 'Boleto', 'recibo': 'Recibo de Pagamento', 'documento': 'Documento(s)'}.get(tipo, tipo)

    if anexos is None:
        ext = os.path.splitext(nome_arquivo)[1].lower() if nome_arquivo else '.pdf'
        mime = 'application/pdf' if ext == '.pdf' else 'application/octet-stream'
        anexos = [(nome_arquivo, dados, mime)]

    n = len(anexos)
    corpo = f"""
      <p>Prezado(a),</p>
      <p>Segue em anexo {'o' if n == 1 else 'os'} <strong>{tipo_label}</strong>
         referente{'s' if n > 1 else ''} à competência de <strong>{mes_nome} de {ano}</strong>.</p>
      <p>{'O arquivo também está' if n == 1 else 'Os arquivos também estão'} disponível{'is' if n > 1 else ''}
         para download na seção correspondente do portal.</p>
    """
    send_email(
        destinatarios=emails,
        assunto=f'{tipo_label} — {mes_nome}/{ano} | {empresa.razao_social}',
        corpo_html=email_html(corpo),
        anexos=anexos,
    )


def _enviar_lote_por_email(emails_lote: dict, mes_nome: str, ano: int, tipo: str):
    """Envia emails em lote após commit — um email por empresa com seus anexos."""
    from app.models.email_empresa import EmailEmpresa
    from app.utils.email import send_email, email_html

    tipo_label = {'boleto': 'Boleto', 'recibo': 'Recibo de Pagamento', 'documento': 'Documento(s)'}.get(tipo, tipo)

    for empresa_id, info in emails_lote.items():
        emails = [e.email for e in EmailEmpresa.query.filter_by(empresa_id=empresa_id).all()]
        if not emails:
            continue
        n = len(info['arquivos'])
        corpo = f"""
          <p>Prezado(a),</p>
          <p>Segue em anexo {'o' if n == 1 else 'os'} <strong>{tipo_label}</strong>
             referente{'s' if n > 1 else ''} à competência de <strong>{mes_nome} de {ano}</strong>.</p>
          <p>{'O arquivo também está' if n == 1 else 'Os arquivos também estão'} disponível{'is' if n > 1 else ''}
             para download na seção correspondente do portal.</p>
        """
        send_email(
            destinatarios=emails,
            assunto=f'{tipo_label} — {mes_nome}/{ano} | {info["razao"]}',
            corpo_html=email_html(corpo),
            anexos=info['arquivos'],
        )


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
    tab = request.args.get('tab', 'dados')
    return render_template('area_admin/empresa_form.html',
                           active='empresas', empresa=empresa, tab_ativa=tab)


@admin_bp.route('/empresas/<int:id>/emails/adicionar', methods=['POST'])
@admin_required
def empresa_email_adicionar(id):
    empresa = Empresa.query.get_or_404(id)
    email = request.form.get('email', '').strip().lower()
    nome_contato = request.form.get('nome_contato', '').strip() or None
    if not email or '@' not in email:
        flash('Endereço de e-mail inválido.', 'erro')
        return redirect(url_for('area_admin.empresa_editar', id=id, tab='emails'))
    ja_existe = EmailEmpresa.query.filter_by(empresa_id=id, email=email).first()
    if ja_existe:
        flash('Este e-mail já está cadastrado para essa empresa.', 'erro')
        return redirect(url_for('area_admin.empresa_editar', id=id, tab='emails'))
    db.session.add(EmailEmpresa(empresa_id=id, email=email, nome_contato=nome_contato))
    db.session.commit()
    flash(f'E-mail {email} adicionado.', 'sucesso')
    return redirect(url_for('area_admin.empresa_editar', id=id, tab='emails'))


@admin_bp.route('/empresas/<int:empresa_id>/emails/<int:email_id>/excluir', methods=['POST'])
@admin_required
def empresa_email_excluir(empresa_id, email_id):
    entry = EmailEmpresa.query.filter_by(id=email_id, empresa_id=empresa_id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash('E-mail removido.', 'sucesso')
    return redirect(url_for('area_admin.empresa_editar', id=empresa_id, tab='emails'))


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

        if role == 'cliente':
            empresa_id = request.form.get('empresa_id', type=int)
            if not empresa_id or not Empresa.query.get(empresa_id):
                flash('Selecione uma empresa válida.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))
            cpf = request.form.get('cpf', '').strip() or None
            if cpf and Usuario.query.filter_by(cpf=cpf).first():
                flash('Já existe um usuário com esse CPF.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))
        else:
            cpf = request.form.get('cpf', '').strip() or None
            if not cpf:
                flash('CPF é obrigatório para colaboradores e administradores.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))
            if Usuario.query.filter_by(cpf=cpf).first():
                flash('Já existe um usuário com esse CPF.', 'erro')
                return redirect(url_for('area_admin.usuario_novo'))
            empresa_id = escritorio.id if escritorio else None

        senha = _gerar_senha_temp()
        u = Usuario(nome=nome, email=email, role=role, cpf=cpf,
                    empresa_id=empresa_id, ativo=True, senha_temporaria=True,
                    senha_temp_texto=senha)
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

        escritorio = Empresa.query.filter_by(cnpj='00.000.000/0001-00').first()

        if role == 'cliente':
            empresa_id = request.form.get('empresa_id', type=int)
            if not empresa_id or not Empresa.query.get(empresa_id):
                flash('Selecione uma empresa válida.', 'erro')
                return redirect(url_for('area_admin.usuario_editar', id=id))
            cpf = request.form.get('cpf', '').strip() or None
            if cpf:
                conflito_cpf = Usuario.query.filter(Usuario.cpf == cpf, Usuario.id != id).first()
                if conflito_cpf:
                    flash('Já existe outro usuário com esse CPF.', 'erro')
                    return redirect(url_for('area_admin.usuario_editar', id=id))
        else:
            cpf = request.form.get('cpf', '').strip() or None
            if not cpf:
                flash('CPF é obrigatório para colaboradores e administradores.', 'erro')
                return redirect(url_for('area_admin.usuario_editar', id=id))
            conflito_cpf = Usuario.query.filter(Usuario.cpf == cpf, Usuario.id != id).first()
            if conflito_cpf:
                flash('Já existe outro usuário com esse CPF.', 'erro')
                return redirect(url_for('area_admin.usuario_editar', id=id))
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
    usuario.senha_temp_texto = senha
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

    caminho, nome_original, tamanho, dados_arquivo = resultado
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

    if request.form.get('enviar_email') == 'on':
        _enviar_arquivo_por_email(empresa_id, mes, ano, nome_original, dados_arquivo, 'boleto')

    flash('Boleto enviado com sucesso.', 'sucesso')
    return redirect(url_for('area_admin.boletos'))


@admin_bp.route('/boletos/lote', methods=['POST'])
@admin_required
def boleto_lote():
    import re
    from io import BytesIO

    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)
    arquivos = request.files.getlist('arquivos')

    if not mes or not ano or not any(a.filename for a in arquivos):
        flash('Preencha mês, ano e selecione ao menos um arquivo.', 'erro')
        return redirect(url_for('area_admin.boletos'))
    if not (1 <= mes <= 12):
        flash('Mês inválido.', 'erro')
        return redirect(url_for('area_admin.boletos'))

    try:
        import pdfplumber
    except ImportError:
        flash('pdfplumber não instalado. Execute: pip install pdfplumber', 'erro')
        return redirect(url_for('area_admin.boletos'))

    CNPJ_RE = re.compile(r'CNPJ/CPF:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})')
    CNPJ_ESCRITORIO = '03.997.535/0001-77'

    enviar_email = request.form.get('enviar_email') == 'on'
    enviados, sem_cadastro, com_erro = [], [], []
    empresas_notificar = {}  # empresa_id → razao_social
    emails_lote: dict[int, dict] = {}  # empresa_id → {razao, arquivos}

    for arq in arquivos:
        if not arq or not arq.filename:
            continue
        if not arq.filename.lower().endswith('.pdf'):
            com_erro.append({'nome': arq.filename, 'motivo': 'Não é PDF'})
            continue

        data = arq.read()

        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                texto = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            cnpjs = CNPJ_RE.findall(texto)
            cnpj = next((c for c in cnpjs if c != CNPJ_ESCRITORIO), None)
        except Exception:
            com_erro.append({'nome': arq.filename, 'motivo': 'Erro ao ler PDF'})
            continue

        if not cnpj:
            com_erro.append({'nome': arq.filename, 'motivo': 'CNPJ não encontrado no PDF'})
            continue

        empresa = Empresa.query.filter_by(cnpj=cnpj).first()
        if not empresa:
            sem_cadastro.append({'nome': arq.filename, 'cnpj': cnpj})
            continue

        nome_dest = f'{ano}{mes:02d}_{uuid.uuid4().hex[:8]}_{arq.filename}'
        key = f'boletos/{empresa.id}/{nome_dest}'
        storage.save(data, key)

        existente = Boleto.query.filter_by(
            empresa_id=empresa.id, competencia_mes=mes, competencia_ano=ano
        ).first()
        if existente:
            storage.delete(existente.caminho_arquivo)
            existente.nome_original = arq.filename
            existente.caminho_arquivo = key
            existente.tamanho_bytes = len(data)
            existente.enviado_em = datetime.now()
            existente.enviado_por_id = current_user.id
            existente.status = 'pendente'
            existente.recebido_em = None
            acao = 'atualizado'
        else:
            db.session.add(Boleto(
                empresa_id=empresa.id,
                competencia_mes=mes,
                competencia_ano=ano,
                nome_original=arq.filename,
                caminho_arquivo=key,
                tamanho_bytes=len(data),
                enviado_por_id=current_user.id,
            ))
            acao = 'inserido'

        empresas_notificar[empresa.id] = empresa.razao_social
        enviados.append({'empresa': empresa.razao_social, 'nome': arq.filename, 'acao': acao})
        if enviar_email:
            emails_lote.setdefault(empresa.id, {'razao': empresa.razao_social, 'arquivos': []})
            emails_lote[empresa.id]['arquivos'].append((arq.filename, data, 'application/pdf'))

    mes_nome = MESES_NOMES[mes - 1]
    for empresa_id in empresas_notificar:
        db.session.add(Comunicado(
            titulo=f'Boleto de {mes_nome} {ano} disponível',
            conteudo=(
                f'Seu boleto referente à competência de {mes_nome} de {ano} '
                'está disponível para download na seção Boletos do portal.'
            ),
            para_todos=False,
            empresa_id=empresa_id,
        ))

    db.session.commit()

    if enviar_email:
        _enviar_lote_por_email(emails_lote, mes_nome, ano, 'boleto')

    return render_template('area_admin/boletos_lote_resultado.html',
        active='boletos',
        mes_nome=mes_nome,
        ano=ano,
        enviados=enviados,
        sem_cadastro=sem_cadastro,
        com_erro=com_erro,
    )


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

    caminho, nome_original, tamanho, dados_arquivo = resultado
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

    if request.form.get('enviar_email') == 'on':
        _enviar_arquivo_por_email(empresa_id, mes, ano, nome_original, dados_arquivo, 'recibo')

    flash('Recibo enviado com sucesso.', 'sucesso')
    return redirect(url_for('area_admin.recibos'))


@admin_bp.route('/recibos/lote', methods=['POST'])
@admin_required
def recibo_lote():
    import re
    from io import BytesIO

    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)
    arquivos = request.files.getlist('arquivos')

    if not mes or not ano or not any(a.filename for a in arquivos):
        flash('Preencha mês, ano e selecione ao menos um arquivo.', 'erro')
        return redirect(url_for('area_admin.recibos'))
    if not (1 <= mes <= 12):
        flash('Mês inválido.', 'erro')
        return redirect(url_for('area_admin.recibos'))

    try:
        import pdfplumber
    except ImportError:
        flash('pdfplumber não instalado. Execute: pip install pdfplumber', 'erro')
        return redirect(url_for('area_admin.recibos'))

    CNPJ_RE = re.compile(r'CNPJ/CPF:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})')
    CNPJ_ESCRITORIO = '03.997.535/0001-77'

    enviar_email = request.form.get('enviar_email') == 'on'
    enviados, sem_cadastro, com_erro = [], [], []
    empresas_notificar = {}
    emails_lote: dict[int, dict] = {}

    for arq in arquivos:
        if not arq or not arq.filename:
            continue
        if not arq.filename.lower().endswith('.pdf'):
            com_erro.append({'nome': arq.filename, 'motivo': 'Não é PDF'})
            continue

        data = arq.read()

        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                texto = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            cnpjs = CNPJ_RE.findall(texto)
            cnpj = next((c for c in cnpjs if c != CNPJ_ESCRITORIO), None)
        except Exception:
            com_erro.append({'nome': arq.filename, 'motivo': 'Erro ao ler PDF'})
            continue

        if not cnpj:
            com_erro.append({'nome': arq.filename, 'motivo': 'CNPJ não encontrado no PDF'})
            continue

        empresa = Empresa.query.filter_by(cnpj=cnpj).first()
        if not empresa:
            sem_cadastro.append({'nome': arq.filename, 'cnpj': cnpj})
            continue

        nome_dest = f'{ano}{mes:02d}_{uuid.uuid4().hex[:8]}_{arq.filename}'
        key = f'recibos/{empresa.id}/{nome_dest}'
        storage.save(data, key)

        existente = Recibo.query.filter_by(
            empresa_id=empresa.id, competencia_mes=mes, competencia_ano=ano
        ).first()
        if existente:
            storage.delete(existente.caminho_arquivo)
            existente.nome_original = arq.filename
            existente.caminho_arquivo = key
            existente.tamanho_bytes = len(data)
            existente.enviado_em = datetime.now()
            existente.enviado_por_id = current_user.id
            existente.status = 'pendente'
            existente.recebido_em = None
            acao = 'atualizado'
        else:
            db.session.add(Recibo(
                empresa_id=empresa.id,
                competencia_mes=mes,
                competencia_ano=ano,
                nome_original=arq.filename,
                caminho_arquivo=key,
                tamanho_bytes=len(data),
                enviado_por_id=current_user.id,
            ))
            acao = 'inserido'

        empresas_notificar[empresa.id] = empresa.razao_social
        enviados.append({'empresa': empresa.razao_social, 'nome': arq.filename, 'acao': acao})
        if enviar_email:
            emails_lote.setdefault(empresa.id, {'razao': empresa.razao_social, 'arquivos': []})
            emails_lote[empresa.id]['arquivos'].append((arq.filename, data, 'application/pdf'))

    mes_nome = MESES_NOMES[mes - 1]
    for empresa_id in empresas_notificar:
        db.session.add(Comunicado(
            titulo=f'Recibo de {mes_nome} {ano} disponível',
            conteudo=(
                f'Seu recibo referente à competência de {mes_nome} de {ano} '
                'está disponível para download na seção Recibos do portal.'
            ),
            para_todos=False,
            empresa_id=empresa_id,
        ))

    db.session.commit()

    if enviar_email:
        _enviar_lote_por_email(emails_lote, mes_nome, ano, 'recibo')

    return render_template('area_admin/recibos_lote_resultado.html',
        active='recibos',
        mes_nome=mes_nome,
        ano=ano,
        enviados=enviados,
        sem_cadastro=sem_cadastro,
        com_erro=com_erro,
    )


@admin_bp.route('/recibos/<int:id>/excluir', methods=['POST'])
@admin_required
def recibo_excluir(id):
    recibo = Recibo.query.get_or_404(id)
    storage.delete(recibo.caminho_arquivo)
    db.session.delete(recibo)
    db.session.commit()
    flash('Recibo excluído.', 'sucesso')
    return redirect(url_for('area_admin.recibos'))


# ──────────────────────────────────────────────
# DOCUMENTOS
# ──────────────────────────────────────────────

@admin_bp.route('/documentos')
@admin_required
def documentos():
    empresa_filtro = request.args.get('empresa_id', type=int)
    mes_filtro = request.args.get('mes', type=int)
    ano_filtro = request.args.get('ano', type=int)
    q = Documento.query
    if empresa_filtro:
        q = q.filter_by(empresa_id=empresa_filtro)
    if mes_filtro:
        q = q.filter_by(competencia_mes=mes_filtro)
    if ano_filtro:
        q = q.filter_by(competencia_ano=ano_filtro)
    lista = q.order_by(
        Documento.competencia_ano.desc(),
        Documento.competencia_mes.desc(),
        Documento.enviado_em.desc(),
    ).all()
    empresas_lista = Empresa.query.filter(
        Empresa.cnpj != '00.000.000/0001-00',
        Empresa.ativo == True
    ).order_by(Empresa.razao_social).all()
    return render_template('area_admin/documentos.html',
        active='documentos',
        documentos=lista,
        empresas=empresas_lista,
        empresa_filtro=empresa_filtro,
        mes_filtro=mes_filtro,
        ano_filtro=ano_filtro,
        meses=MESES_NOMES,
        ano_atual=datetime.now().year,
    )


@admin_bp.route('/documentos/upload', methods=['POST'])
@admin_required
def documento_upload():
    empresa_id = request.form.get('empresa_id', type=int)
    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)

    if not empresa_id or not mes or not ano:
        flash('Preencha empresa, mês e ano.', 'erro')
        return redirect(url_for('area_admin.documentos'))
    if not (1 <= mes <= 12):
        flash('Mês inválido.', 'erro')
        return redirect(url_for('area_admin.documentos'))

    arquivos = request.files.getlist('arquivos')
    arquivos = [a for a in arquivos if a and a.filename]
    if not arquivos:
        flash('Selecione ao menos um arquivo.', 'erro')
        return redirect(url_for('area_admin.documentos'))

    enviados = 0
    anexos_email = []
    for arq in arquivos:
        dados = arq.read()
        if len(dados) > 50 * 1024 * 1024:
            flash(f'{arq.filename}: arquivo excede 50 MB.', 'erro')
            continue
        nome_dest = f'{ano}{mes:02d}_{uuid.uuid4().hex[:8]}_{arq.filename}'
        key = f'documentos/{empresa_id}/{nome_dest}'
        storage.save(dados, key)
        db.session.add(Documento(
            empresa_id=empresa_id,
            competencia_mes=mes,
            competencia_ano=ano,
            nome_original=arq.filename,
            caminho_arquivo=key,
            tamanho_bytes=len(dados),
            enviado_por_id=current_user.id,
        ))
        anexos_email.append((arq.filename, dados, 'application/pdf'))
        enviados += 1

    if enviados:
        mes_nome = MESES_NOMES[mes - 1]
        db.session.add(Comunicado(
            titulo=f'Documentos de {mes_nome} {ano} disponíveis',
            conteudo=(
                f'{enviados} documento(s) referente(s) à competência de {mes_nome} de {ano} '
                'estão disponíveis para download na seção Documentos do portal.'
            ),
            para_todos=False,
            empresa_id=empresa_id,
        ))
        db.session.commit()

        if request.form.get('enviar_email') == 'on':
            _enviar_arquivo_por_email(empresa_id, mes, ano, None, None, 'documento', anexos_email)

        flash(f'{enviados} documento(s) enviado(s) com sucesso.', 'sucesso')

    return redirect(url_for('area_admin.documentos'))


@admin_bp.route('/documentos/lote', methods=['POST'])
@admin_required
def documento_lote():
    mes = request.form.get('mes', type=int)
    ano = request.form.get('ano', type=int)
    arquivos = request.files.getlist('arquivos')

    if not mes or not ano or not any(a.filename for a in arquivos):
        flash('Preencha mês, ano e selecione a pasta.', 'erro')
        return redirect(url_for('area_admin.documentos'))
    if not (1 <= mes <= 12):
        flash('Mês inválido.', 'erro')
        return redirect(url_for('area_admin.documentos'))

    enviar_email = request.form.get('enviar_email') == 'on'
    mes_nome = MESES_NOMES[mes - 1]
    enviados_map: dict[int, dict] = {}    # empresa_id → {empresa, arquivos}
    pulados_map: dict[int, dict] = {}     # empresa_id → {empresa, arquivos}
    sem_cadastro_map: dict[str, dict] = {}  # pasta → {pasta, arquivos}
    com_erro: list[dict] = []
    empresas_notificar: dict[int, str] = {}
    emails_lote: dict[int, dict] = {}

    # Agrupa arquivos por subpasta (empresa)
    grupos: dict[str, list] = {}
    for arq in arquivos:
        if not arq or not arq.filename:
            continue
        partes = arq.filename.replace('\\', '/').split('/')
        pasta_empresa = partes[-2] if len(partes) >= 2 else ''
        grupos.setdefault(pasta_empresa, []).append(arq)

    for pasta_empresa, arqs in sorted(grupos.items()):
        empresa = Empresa.query.filter(
            db.func.lower(Empresa.razao_social) == db.func.lower(pasta_empresa),
            Empresa.cnpj != '00.000.000/0001-00',
        ).first()
        if not empresa:
            empresa = Empresa.query.filter(
                Empresa.razao_social.ilike(f'%{pasta_empresa}%'),
                Empresa.cnpj != '00.000.000/0001-00',
            ).first()
        if not empresa:
            entry = sem_cadastro_map.setdefault(pasta_empresa, {'pasta': pasta_empresa, 'arquivos': []})
            for a in arqs:
                entry['arquivos'].append(a.filename.split('/')[-1])
            continue

        # Verifica se já existe documento dessa competência para esta empresa
        existente = Documento.query.filter_by(
            empresa_id=empresa.id,
            competencia_mes=mes,
            competencia_ano=ano,
        ).first()
        if existente:
            entry = pulados_map.setdefault(empresa.id, {'empresa': empresa.razao_social, 'arquivos': []})
            for a in arqs:
                entry['arquivos'].append(a.filename.split('/')[-1])
            continue

        entry = enviados_map.setdefault(empresa.id, {'empresa': empresa.razao_social, 'arquivos': []})
        for arq in arqs:
            dados = arq.read()
            if len(dados) > 50 * 1024 * 1024:
                com_erro.append({'nome': arq.filename.split('/')[-1], 'motivo': 'Excede 50 MB'})
                continue
            nome_dest = f'{ano}{mes:02d}_{uuid.uuid4().hex[:8]}_{arq.filename.split("/")[-1]}'
            key = f'documentos/{empresa.id}/{nome_dest}'
            storage.save(dados, key)
            db.session.add(Documento(
                empresa_id=empresa.id,
                competencia_mes=mes,
                competencia_ano=ano,
                nome_original=arq.filename.split('/')[-1],
                caminho_arquivo=key,
                tamanho_bytes=len(dados),
                enviado_por_id=current_user.id,
            ))
            empresas_notificar[empresa.id] = empresa.razao_social
            entry['arquivos'].append(arq.filename.split('/')[-1])
            if enviar_email:
                emails_lote.setdefault(empresa.id, {'razao': empresa.razao_social, 'arquivos': []})
                emails_lote[empresa.id]['arquivos'].append(
                    (arq.filename.split('/')[-1], dados, 'application/pdf'))

    enviados = list(enviados_map.values())
    pulados = list(pulados_map.values())
    sem_cadastro = list(sem_cadastro_map.values())

    for eid, razao in empresas_notificar.items():
        db.session.add(Comunicado(
            titulo=f'Documentos de {mes_nome} {ano} disponíveis',
            conteudo=(
                f'Documentos referentes à competência de {mes_nome} de {ano} '
                'estão disponíveis para download na seção Documentos do portal.'
            ),
            para_todos=False,
            empresa_id=eid,
        ))

    db.session.commit()

    if enviar_email:
        _enviar_lote_por_email(emails_lote, mes_nome, ano, 'documento')

    return render_template('area_admin/documentos_lote_resultado.html',
        active='documentos',
        mes_nome=mes_nome,
        ano=ano,
        enviados=enviados,
        sem_cadastro=sem_cadastro,
        com_erro=com_erro,
        pulados=pulados,
    )


@admin_bp.route('/documentos/<int:id>/excluir', methods=['POST'])
@admin_required
def documento_excluir(id):
    doc = Documento.query.get_or_404(id)
    storage.delete(doc.caminho_arquivo)
    db.session.delete(doc)
    db.session.commit()
    flash('Documento excluído.', 'sucesso')
    return redirect(url_for('area_admin.documentos'))
