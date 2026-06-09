# Portal Barros & Barros — Briefing do Projeto

> Este arquivo é lido automaticamente pelo Claude Code no início de cada sessão.
> Mantenha-o atualizado sempre que houver mudanças estruturais relevantes.

---

## Visão Geral

Portal web para o escritório de contabilidade **Barros & Barros**. Clientes acessam uma área dedicada para abrir chamados, ler comunicados e acompanhar o andamento dos serviços. Colaboradores e admins atendem via kanban interno.

**Stack:** Python 3 · Flask 3.0.3 · Flask-SQLAlchemy (SQLite) · Flask-Login · Jinja2 · HTML/CSS vanilla (sem frameworks JS/CSS externos)

---

## Estrutura de Diretórios

```
Portal_BeB/
├── CLAUDE.md                   ← este arquivo
├── regras_de_negocio.txt       ← regras e requisitos do cliente (fonte da verdade)
├── logins_teste.txt            ← credenciais de teste para ambiente local
├── index.html / portal.html    ← páginas estáticas de apresentação
└── backend/
    ├── run.py                  ← entrypoint; cria tabelas e seed na 1ª execução
    ├── requirements.txt
    ├── instance/               ← barros.db (gerado; excluído do git)
    ├── uploads/                ← arquivos enviados pelos colaboradores (excluído do git)
    ├── app/
    │   ├── __init__.py         ← create_app(), blueprints, context processors
    │   ├── config.py
    │   ├── extensions.py       ← db, login_manager
    │   ├── models/
    │   │   ├── empresa.py
    │   │   ├── usuario.py
    │   │   ├── chamado.py
    │   │   ├── comunicado.py
    │   │   ├── anexo_chamado.py
    │   │   └── historico_chamado.py
    │   ├── blueprints/
    │   │   ├── auth/           ← login, logout, trocar senha
    │   │   ├── area_cliente/   ← início, chamados, comunicados, detalhe
    │   │   └── area_colab/     ← kanban, ações de chamado, anexos, comunicados
    │   └── utils/
    │       ├── seed.py         ← dados de teste
    │       ├── prazo.py        ← cálculo de prazo em dias úteis
    │       └── historico.py    ← helper para registrar HistoricoChamado
    └── views/
        ├── auth/
        ├── area_cliente/
        └── area_colab/
```

---

## Modelos de Dados

### Empresa
- `id`, `cnpj` (unique), `razao_social`, `ativo`
- Empresas clientes têm CNPJ próprio. O escritório tem CNPJ `00.000.000/0001-00`.

### Usuario
- `id`, `nome`, `email`, `senha_hash`, `role` (`cliente` | `operador` | `admin`), `ativo`, `senha_temporaria`
- `empresa_id` → FK para Empresa
- `chamados_atribuidos` = relationship para Chamado (backref `responsavel` já definido aqui — **não redefina em Chamado**)

### Chamado
- Campos principais: `numero`, `tipo`, `titulo`, `descricao`, `nome_funcionario`, `tipo_certidao`, `status`, `empresa_id`, `usuario_id`, `atribuido_a`, `atribuido_em`, `prazo_limite`
- Campos de auditoria: `devolvido_por_nome`, `finalizado_por_nome`, `finalizado_em`, `editado_por_nome`, `editado_em`
- **Status possíveis:** `pendente` · `em_realizacao` · `devolvido` · `finalizado`
- `responsavel` é acessado via backref criado em `Usuario.chamados_atribuidos` — não declare novamente em `chamado.py`

### AnexoChamado
- Arquivos enviados por colaboradores. Armazenados em `backend/uploads/<chamado_id>/<uuid>.<ext>`
- Tipos permitidos: `.pdf .docx .xlsx .png .jpg .jpeg .zip` · Limite: 10 MB

### HistoricoChamado
- Log imutável de cada ação sobre um chamado
- Ações: `aberto` · `pego` · `devolvido` · `finalizado` · `anexo_enviado`
- Ordem padrão: **decrescente** (mais recente primeiro)

### Comunicado
- `empresa_id = NULL` → para todos os clientes
- `empresa_id = X`  → apenas para a empresa X
- Leitura rastreada por `ComunicadoLeitura` (empresa_id, comunicado_id)

---

## Regras de Negócio Críticas

### Upload de documentos
- **Somente o colaborador que assumiu o chamado** (`atribuido_a == current_user.id`) pode enviar arquivos.
- Admin pode enviar em qualquer chamado.
- O form de upload fica oculto para quem não é o responsável.
- A rota `POST /colab/chamados/<id>/anexos` valida isso server-side antes de salvar.

### Prazo em dias úteis (`utils/prazo.py`)
- Dias úteis: segunda a sexta, 08:00–18:00
- Prazos configurados em `PRAZOS_DIAS`: rescisão=1d, certidão=1d, notas_fiscais=3d
- Se o chamado for aberto fora do horário comercial, o prazo começa a contar a partir das 08:00 do próximo dia útil

### Semáforo de prazo (`chamado.semaforo`)
- `verde` → mais de 8h restantes
- `amarelo` → 0–8h restantes
- `vermelho` → prazo vencido

### Kanban (area_colab)
- **Em Aberto:** status `pendente` ou `devolvido` sem `atribuido_a`
- **Realizando:** status `em_realizacao`
- **Finalizado:** status `finalizado` (com filtros por empresa/tipo/colaborador/data)
- Devolver um chamado limpa `atribuido_a` e volta para Em Aberto

### Login multi-usuário por CNPJ
- Escritório (CNPJ `00.000.000/0001-00`) tem múltiplos usuários (operador + admin)
- O `auth/routes.py` itera todos os usuários ativos da empresa e testa a senha individualmente
- **Não use `query.filter_by(...).first()` antes de checar senha**

### Comunicados filtrados por empresa
- Cliente só vê comunicados onde `empresa_id IS NULL` OR `empresa_id == current_user.empresa_id`
- Sidebar mostra contagem de não-lidos aplicando o mesmo filtro

### Auto-comunicado na finalização
- Ao finalizar um chamado, a rota cria automaticamente um `Comunicado` para a empresa do cliente, informando a conclusão e quantidade de documentos disponíveis

---

## Roles e Redirecionamentos

| Role      | Redireciona para          |
|-----------|---------------------------|
| cliente   | `/cliente/inicio`         |
| operador  | `/colab/dashboard`        |
| admin     | `/colab/dashboard`        |

---

## Como Iniciar Localmente

```bash
cd backend
pip install -r requirements.txt
python run.py
# Acesse http://localhost:5000
# Banco criado e seed executado na 1ª execução
```

Para resetar: apague `backend/instance/barros.db` e reinicie.

---

## Fase Atual: Fase 2 — Concluída (09/06/2026)

**Implementado:**
- Kanban completo (Em Aberto / Realizando / Finalizado)
- Pegar, devolver (com motivo) e finalizar chamados (com modal de confirmação)
- Upload e download autenticado de arquivos por chamado
- Histórico de auditoria por chamado (ordem decrescente)
- Cálculo de prazo em dias úteis
- Comunicados com filtro por empresa e rastreamento de leitura
- Criação de comunicado (para todos ou empresa específica)
- Auto-comunicado ao cliente quando chamado é finalizado
- Detalhe do chamado para o cliente (steps de progresso + downloads)
- Upload restrito ao responsável do chamado

**Próximas fases (não iniciadas):**
- Área admin dedicada (gestão de usuários e empresas)
- Boletos
- Documentos / Certidões
- Timezone (produção usa horário local; configurar para fuso de Brasília em deploy)
- Deploy com WSGI server (Gunicorn) + HTTPS

---

## Armadilhas Conhecidas

1. **Backref `responsavel`** — já definido em `Usuario.chamados_atribuidos`. Se redefinir em `Chamado`, SQLAlchemy levanta `ArgumentError` na inicialização.
2. **`datetime.utcnow` depreciado** — use `datetime.now()` (sem UTC) enquanto não há timezone configurado.
3. **`db.session.flush()`** — necessário para obter IDs de objetos ainda não commitados ao gerar registros relacionados no seed.
4. **Nomes de repositório** — GitHub não aceita `&` em nomes de repo; o repositório usa `Portal_BeB`.
