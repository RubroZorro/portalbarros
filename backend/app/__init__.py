import os
from flask import Flask, redirect, url_for, flash, render_template
from app.config import DevConfig, ProdConfig
from app.extensions import db, login_manager, limiter, csrf


def create_app():
    env = os.environ.get('FLASK_ENV', 'development')
    config = ProdConfig if env == 'production' else DevConfig
    app = Flask(__name__, template_folder='../views')
    app.config.from_object(config)

    # Pasta de uploads fora da raiz web
    app.config['UPLOAD_FOLDER'] = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'uploads'
    )

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)

    @app.errorhandler(429)
    def ratelimit_handler(e):
        flash('Muitas tentativas de acesso. Aguarde alguns minutos e tente novamente.', 'erro')
        return render_template('auth/login.html'), 429

    from app.blueprints.auth import auth_bp
    from app.blueprints.area_cliente import cliente_bp
    from app.blueprints.area_admin import admin_bp
    from app.blueprints.area_colab import colab_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(cliente_bp, url_prefix='/cliente')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(colab_bp, url_prefix='/colab')

    # garante criação de todas as tabelas ao iniciar (necessário com Gunicorn em prod)
    with app.app_context():
        db.create_all()
        # migração incremental: adiciona coluna se ainda não existir
        with db.engine.connect() as _conn:
            for stmt in [
                'ALTER TABLE usuarios ADD COLUMN senha_temp_texto VARCHAR(50)',
                'ALTER TABLE chamados ADD COLUMN outro_solicitante VARCHAR(200)',
            ]:
                try:
                    _conn.execute(db.text(stmt))
                    _conn.commit()
                except Exception:
                    pass

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from datetime import datetime

        meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        dias_semana = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira',
                       'Sexta-feira', 'Sábado', 'Domingo']
        now = datetime.now()
        data_hoje = f'{dias_semana[now.weekday()]}, {now.day} de {meses[now.month - 1]} de {now.year}'

        nao_lidos_sidebar = 0
        if current_user.is_authenticated and current_user.empresa_id:
            from app.models.comunicado import Comunicado, ComunicadoLeitura
            lidas = db.session.query(ComunicadoLeitura.comunicado_id).filter_by(
                usuario_id=current_user.id
            ).subquery()
            nao_lidos_sidebar = Comunicado.query.filter(
                db.or_(
                    Comunicado.empresa_id.is_(None),
                    Comunicado.empresa_id == current_user.empresa_id
                ),
                ~Comunicado.id.in_(lidas)
            ).count()

        return {'nao_lidos_sidebar': nao_lidos_sidebar, 'data_hoje': data_hoje}

    return app
