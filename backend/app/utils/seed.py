from app.extensions import db
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.models.chamado import Chamado
from app.models.comunicado import Comunicado
from app.models.historico_chamado import HistoricoChamado
from app.utils.prazo import calcular_prazo
from datetime import datetime, timedelta


def seed_database():
    empresa_cliente = Empresa(cnpj='12.345.678/0001-90', razao_social='Empresa Teste Ltda')
    empresa_escritorio = Empresa(cnpj='00.000.000/0001-00', razao_social='Barros & Barros Contabilidade')
    db.session.add_all([empresa_cliente, empresa_escritorio])
    db.session.flush()

    cliente = Usuario(nome='Maria Silva', email='maria@empresa.com', role='cliente',
                      empresa_id=empresa_cliente.id, senha_temporaria=False)
    cliente.set_password('Teste@123')

    admin = Usuario(nome='Admin Barros', email='admin@barros.com', role='admin',
                    cpf='111.111.111-11',
                    empresa_id=empresa_escritorio.id, senha_temporaria=False)
    admin.set_password('Admin@123')

    operador = Usuario(nome='João Operador', email='joao@barros.com', role='operador',
                       cpf='222.222.222-22',
                       empresa_id=empresa_escritorio.id, senha_temporaria=False)
    operador.set_password('Oper@123')

    db.session.add_all([cliente, admin, operador])
    db.session.flush()

    comunicados = [
        Comunicado(titulo='Declaração de IR 2026 — Prazo Final',
                   conteudo='O prazo para entrega da sua documentação para a declaração de Imposto de Renda 2026 é 30/06. Não deixe para a última hora — organize seus comprovantes com antecedência.',
                   created_at=datetime.now() - timedelta(days=2)),
        Comunicado(titulo='Guia DASN-SIMEI — Junho 2026',
                   conteudo='A guia do DASN-SIMEI referente a junho de 2026 está disponível. Confira os valores e efetue o pagamento até o vencimento para evitar juros e multa.',
                   created_at=datetime.now() - timedelta(days=4)),
        Comunicado(titulo='Recesso de Corpus Christi',
                   conteudo='Nosso escritório estará fechado nos dias 19 e 20 de junho. Retornamos normalmente na segunda-feira, dia 23.',
                   created_at=datetime.now() - timedelta(days=8)),
        Comunicado(titulo='Atualização no regime tributário',
                   conteudo='Houve atualização nas tabelas do Simples Nacional para o segundo semestre. Entre em contato caso tenha dúvidas sobre seu enquadramento.',
                   created_at=datetime.now() - timedelta(days=16)),
    ]
    db.session.add_all(comunicados)

    t1 = datetime.now() - timedelta(days=1)
    t2 = datetime.now() - timedelta(days=3)
    t3 = datetime.now() - timedelta(days=10)
    t4 = datetime.now() - timedelta(days=5)

    ch1 = Chamado(
        numero='#0001', tipo='notas_fiscais', titulo='Envio de Notas Fiscais',
        status='em_realizacao',
        atribuido_a=operador.id, atribuido_em=t1 + timedelta(hours=2),
        prazo_limite=calcular_prazo('notas_fiscais', t1),
        empresa_id=empresa_cliente.id, usuario_id=cliente.id,
        created_at=t1,
    )
    ch2 = Chamado(
        numero='#0002', tipo='certidao', titulo='Solicitação de Certidão A',
        tipo_certidao='A', status='pendente',
        prazo_limite=calcular_prazo('certidao', t2),
        empresa_id=empresa_cliente.id, usuario_id=cliente.id,
        created_at=t2,
    )
    ch3 = Chamado(
        numero='#0003', tipo='rescisao', titulo='Cálculo de Rescisão — João Costa',
        nome_funcionario='João Costa', status='finalizado',
        prazo_limite=calcular_prazo('rescisao', t3),
        atribuido_a=operador.id, atribuido_em=t3 + timedelta(hours=1),
        finalizado_por_nome='João Operador',
        finalizado_em=t3 + timedelta(hours=4),
        empresa_id=empresa_cliente.id, usuario_id=cliente.id,
        created_at=t3,
    )
    ch4 = Chamado(
        numero='#0004', tipo='certidao', titulo='Solicitação de Certidão B',
        tipo_certidao='B', status='devolvido',
        devolvido_por_nome='João Operador',
        prazo_limite=calcular_prazo('certidao', t4),
        empresa_id=empresa_cliente.id, usuario_id=cliente.id,
        created_at=t4,
    )
    db.session.add_all([ch1, ch2, ch3, ch4])
    db.session.flush()

    historicos = [
        HistoricoChamado(chamado_id=ch1.id, usuario_id=cliente.id,
                         usuario_nome='Maria Silva', acao='aberto', criado_em=t1),
        HistoricoChamado(chamado_id=ch1.id, usuario_id=operador.id,
                         usuario_nome='João Operador', acao='pego',
                         criado_em=t1 + timedelta(hours=2)),
        HistoricoChamado(chamado_id=ch2.id, usuario_id=cliente.id,
                         usuario_nome='Maria Silva', acao='aberto', criado_em=t2),
        HistoricoChamado(chamado_id=ch3.id, usuario_id=cliente.id,
                         usuario_nome='Maria Silva', acao='aberto', criado_em=t3),
        HistoricoChamado(chamado_id=ch3.id, usuario_id=operador.id,
                         usuario_nome='João Operador', acao='pego',
                         criado_em=t3 + timedelta(hours=1)),
        HistoricoChamado(chamado_id=ch3.id, usuario_id=operador.id,
                         usuario_nome='João Operador', acao='finalizado',
                         criado_em=t3 + timedelta(hours=4)),
        HistoricoChamado(chamado_id=ch4.id, usuario_id=cliente.id,
                         usuario_nome='Maria Silva', acao='aberto', criado_em=t4),
        HistoricoChamado(chamado_id=ch4.id, usuario_id=operador.id,
                         usuario_nome='João Operador', acao='pego',
                         criado_em=t4 + timedelta(hours=1)),
        HistoricoChamado(chamado_id=ch4.id, usuario_id=operador.id,
                         usuario_nome='João Operador', acao='devolvido',
                         detalhe='Motivo: Faltam documentos complementares.',
                         criado_em=t4 + timedelta(hours=3)),
    ]
    db.session.add_all(historicos)
    db.session.commit()
