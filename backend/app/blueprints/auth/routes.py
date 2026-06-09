from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.extensions import db

auth_bp = Blueprint('auth', __name__)


def _cnpj_digits(cnpj: str) -> str:
    return cnpj.replace('.', '').replace('/', '').replace('-', '').strip()


def _redirect_by_role(user, as_url=False):
    routes = {
        'cliente':  'area_cliente.inicio',
        'admin':    'area_colab.dashboard',
        'operador': 'area_colab.dashboard',
    }
    target = url_for(routes.get(user.role, 'auth.login'))
    return target if as_url else redirect(target)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        cnpj_raw = request.form.get('cnpj', '').strip()
        cnpj_digits = _cnpj_digits(cnpj_raw)
        senha = request.form.get('senha', '').strip()

        empresa = Empresa.query.filter(
            db.or_(
                Empresa.cnpj == cnpj_raw,
                Empresa.cnpj == cnpj_digits,
            )
        ).first()

        if not empresa:
            all_empresas = Empresa.query.all()
            for e in all_empresas:
                if _cnpj_digits(e.cnpj) == cnpj_digits:
                    empresa = e
                    break

        if empresa:
            usuario = None
            for u in Usuario.query.filter_by(empresa_id=empresa.id, ativo=True).all():
                if u.check_password(senha):
                    usuario = u
                    break
            if usuario:
                login_user(usuario, remember=bool(request.form.get('lembrar')))
                if usuario.senha_temporaria:
                    return redirect(url_for('auth.trocar_senha'))
                next_page = request.args.get('next')
                return redirect(next_page or _redirect_by_role(usuario, as_url=True))

        flash('CNPJ ou senha incorretos.', 'erro')

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
