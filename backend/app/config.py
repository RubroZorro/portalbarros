import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'bb-dev-secret-2026')
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///barros.db')
    # Render entrega postgres:// mas SQLAlchemy exige postgresql://
    SQLALCHEMY_DATABASE_URI = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    R2_BUCKET     = os.environ.get('R2_BUCKET')
    R2_ENDPOINT   = os.environ.get('R2_ENDPOINT')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY')

    # Flask-WTF
    WTF_CSRF_ENABLED = True

    # Flask-Limiter — usa Redis em prod (REDIS_URL), memória em dev
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
