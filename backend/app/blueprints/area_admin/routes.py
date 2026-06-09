from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps

admin_bp = Blueprint('area_admin', __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    from app.models.chamado import Chamado
    from app.models.empresa import Empresa
    chamados_pendentes = Chamado.query.filter_by(status='pendente').count()
    total_empresas = Empresa.query.filter_by(ativo=True).count()
    chamados_recentes = Chamado.query.order_by(Chamado.created_at.desc()).limit(10).all()
    return render_template('area_admin/dashboard.html',
        active='dashboard',
        chamados_pendentes=chamados_pendentes,
        total_empresas=total_empresas,
        chamados_recentes=chamados_recentes,
    )
