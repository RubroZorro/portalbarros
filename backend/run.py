from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from app.models.usuario import Usuario
        if not Usuario.query.first():
            from app.utils.seed import seed_database
            seed_database()
            print('\nDados de teste criados:')
            print('  Cliente    -> CNPJ: 12.345.678/0001-90  |  Senha: Teste@123')
            print('  Operador   -> CPF:  222.222.222-22       |  Senha: Oper@123')
            print('  Admin      -> CPF:  111.111.111-11       |  Senha: Admin@123')
            print()
    app.run(debug=True, port=5000)
