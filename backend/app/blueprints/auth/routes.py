import re
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.extensions import db, limiter

auth_bp = Blueprint('auth', __name__)


def _so_digitos(valor: str) -> str:
    return re.sub(r'\D', '', valor)


def _redirect_by_role(user, as_url=False):
    routes = {
        'cliente':  'area_cliente.inicio',
        'admin':    'area_admin.dashboard',
        'operador': 'area_colab.dashboard',
    }
    target = url_for(routes.get(user.role, 'auth.login'))
    return target if as_url else redirect(target)


def _autenticar_por_cpf(digitos, senha):
    """Busca usuário pelo CPF e verifica a senha."""
    for u in Usuario.query.filter_by(ativo=True).all():
        if u.cpf and _so_digitos(u.cpf) == digitos and u.check_password(senha):
            return u
    return None


def _autenticar_por_cnpj(cnpj_raw, digitos, senha):
    """Busca empresa pelo CNPJ e itera usuários para verificar a senha."""
    empresa = Empresa.query.filter(
        db.or_(Empresa.cnpj == cnpj_raw, Empresa.cnpj == digitos)
    ).first()
    if not empresa:
        for e in Empresa.query.all():
            if _so_digitos(e.cnpj) == digitos:
                empresa = e
                break
    if empresa:
        for u in Usuario.query.filter_by(empresa_id=empresa.id, ativo=True).all():
            if u.check_password(senha):
                return u
    return None


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 30 per hour')
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        identificador = request.form.get('cnpj', '').strip()
        senha = request.form.get('senha', '').strip()
        digitos = _so_digitos(identificador)

        if len(digitos) == 11:
            usuario = _autenticar_por_cpf(digitos, senha)
        else:
            usuario = _autenticar_por_cnpj(identificador, digitos, senha)

        if usuario:
            login_user(usuario, remember=bool(request.form.get('lembrar')))
            if usuario.senha_temporaria:
                return redirect(url_for('auth.trocar_senha'))
            next_page = request.args.get('next')
            return redirect(next_page or _redirect_by_role(usuario, as_url=True))

        flash('CNPJ, CPF ou senha incorretos.', 'erro')

    return render_template('auth/login.html')


@auth_bp.route('/trocar-senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if not current_user.senha_temporaria:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        nova = request.form.get('nova_senha', '')
        confirma = request.form.get('confirma_senha', '')

        if len(nova) < 8:
            flash('A senha deve ter pelo menos 8 caracteres.', 'erro')
        elif nova != confirma:
            flash('As senhas não coincidem.', 'erro')
        else:
            current_user.set_password(nova)
            current_user.senha_temporaria = False
            db.session.commit()
            flash('Senha definida com sucesso. Bem-vindo ao portal!', 'sucesso')
            return _redirect_by_role(current_user)

    return render_template('auth/trocar_senha.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
