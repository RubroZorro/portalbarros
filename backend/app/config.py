import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'bb-dev-secret-2026')
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///barros.db')
    # Render entrega postgres:// mas SQLAlchemy exige postgresql://
    SQLALCHEMY_DATABASE_URI = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'pool_recycle': 280}

    R2_BUCKET     = os.environ.get('R2_BUCKET')
    R2_ENDPOINT   = os.environ.get('R2_ENDPOINT')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY')

    # Flask-Mail (Gmail SMTP)
    MAIL_SERVER   = 'smtp.gmail.com'
    MAIL_PORT     = 587
    MAIL_USE_TLS  = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'Portal Barros & Barros <barroscontabil@gmail.com>')

    # Flask-WTF
    WTF_CSRF_ENABLED = True

    # Flask-Limiter — usa Redis em prod (REDIS_URL), memória em dev
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
