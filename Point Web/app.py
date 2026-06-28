import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, date
import random
import string
import pytz


app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma-chave-secreta-bem-segura-e-dificil-de-adivinhar'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define o fuso horário de Brasília para exibição
FUSO_HORARIO_BRASILIA = pytz.timezone('America/Sao_Paulo')


class Aluno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_usuario = db.Column(db.String(50), unique=True, nullable=False)
    senha = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    telefone = db.Column(db.String(20))
    nome_completo = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    idade = db.Column(db.Integer)
    naturalidade = db.Column(db.String(50))
    curso = db.Column(db.String(100))
    nivel = db.Column(db.String(50))
    instituicao = db.Column(db.String(100))
    status_academico = db.Column(db.String(50), default='Em Formação')
    presencas = db.relationship('Presenca', backref='aluno', cascade="all, delete-orphan", lazy=True)
    faltas = db.relationship('Falta', backref='aluno', cascade="all, delete-orphan", lazy=True)

class Presenca(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    aluno_id = db.Column(db.Integer, db.ForeignKey('aluno.id'), nullable=False)
    
class Falta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    aluno_id = db.Column(db.Integer, db.ForeignKey('aluno.id'), nullable=False)
    
class Codigo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(6), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expira_em = db.Column(db.DateTime, nullable=False)


@app.context_processor
def injetar_utilitarios():
    def para_horario_brasilia(data_utc):
        if data_utc:
            return data_utc.replace(tzinfo=pytz.utc).astimezone(FUSO_HORARIO_BRASILIA)
        return None
    return dict(para_horario_brasilia=para_horario_brasilia, agora=datetime.now(FUSO_HORARIO_BRASILIA), agora_utc=datetime.utcnow)

# --- ROTAS PRINCIPAIS E DE SESSÃO ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome_usuario = request.form.get('nome_usuario', '').strip()
        senha = request.form.get('senha', '')
        if not nome_usuario or not senha:
            flash('Usuário e senha são obrigatórios.', 'warning')
            return redirect(url_for('login'))
        if nome_usuario == 'admin' and senha == 'admin':
            session['id_usuario'] = 'admin'
            session['tipo_usuario'] = 'admin'
            return redirect(url_for('painel_admin'))
        aluno = Aluno.query.filter_by(nome_usuario=nome_usuario).first()
        if aluno and aluno.senha == senha:
            session['id_usuario'] = aluno.id
            session['tipo_usuario'] = 'aluno'
            return redirect(url_for('painel_aluno'))
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/sair')
def sair():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# --- ROTA DE RECUPERAÇÃO DE SENHA SIMPLIFICADA ---
@app.route('/esqueci_senha')
def esqueci_senha():
    flash('Para redefinir sua senha, por favor, procure o administrador do sistema.', 'info')
    return redirect(url_for('login'))

# --- ROTAS DO ALUNO ---
@app.route('/aluno/painel', methods=['GET', 'POST'])
def painel_aluno():
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'aluno':
        flash('Por favor, faça o login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    aluno = Aluno.query.get(session['id_usuario'])
    if not aluno:
        flash('Erro: Aluno não encontrado. Por favor, faça o login novamente.', 'danger')
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        codigo_inserido = request.form.get('codigo', '').strip().upper()
        if not codigo_inserido:
            flash('Por favor, insira um código.', 'warning')
            return redirect(url_for('painel_aluno'))
        agora_utc = datetime.utcnow()
        codigo_valido = Codigo.query.filter(Codigo.codigo == codigo_inserido, Codigo.expira_em > agora_utc).first()
        if not codigo_valido:
            flash('Código inválido ou expirado!', 'danger')
        else:
            hoje = datetime.now(FUSO_HORARIO_BRASILIA).date()
            ja_validou = Presenca.query.filter_by(aluno_id=aluno.id, data=hoje).first()
            if ja_validou:
                flash('Você já validou a presença hoje.', 'warning')
            else:
                try:
                    db.session.add(Presenca(aluno_id=aluno.id, data=hoje))
                    falta_do_dia = Falta.query.filter_by(aluno_id=aluno.id, data=hoje).first()
                    if falta_do_dia:
                        db.session.delete(falta_do_dia)
                    db.session.commit()
                    flash('Presença validada com sucesso!', 'success')
                except Exception as e:
                    
                    db.session.rollback()
                    flash(f'Ocorreu um erro ao validar a presença: {e}', 'danger')
        return redirect(url_for('painel_aluno'))
    
    total_dias_de_aula = db.session.query(Falta.data).distinct().count()
    presencas_aluno = Presenca.query.filter_by(aluno_id=aluno.id).count()
    frequencia = 0
    if Presenca.query.filter_by(aluno_id=aluno.id, data=datetime.now(FUSO_HORARIO_BRASILIA).date()).first():
        if total_dias_de_aula == 0: total_dias_de_aula = 1
        frequencia = round(((presencas_aluno) / total_dias_de_aula) * 100)
    elif total_dias_de_aula > 0:
        frequencia = round((presencas_aluno / total_dias_de_aula) * 100)
    
    faltas_contagem = Falta.query.filter_by(aluno_id=aluno.id).count()
    return render_template('aluno_home.html', aluno=aluno, frequencia=frequencia, faltas=faltas_contagem)

@app.route('/api/codigos_ativos')
def api_codigos_ativos():
    agora_utc = datetime.utcnow()
    codigos = Codigo.query.filter(Codigo.expira_em > agora_utc).all()
    lista_codigos = [{'codigo': c.codigo, 'expira_em': c.expira_em.isoformat() + "Z"} for c in codigos]
    return jsonify(lista_codigos)

# --- ROTAS DO ADMINISTRADOR ---
@app.route('/admin/painel')
def painel_admin():
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'admin':
        return redirect(url_for('login'))
    try:
        agora_utc = datetime.utcnow()
        codigo_ativo_existente = Codigo.query.filter(Codigo.expira_em > agora_utc).first() is not None
        inicio_do_dia_utc = datetime.combine(datetime.now(FUSO_HORARIO_BRASILIA).date(), datetime.min.time()).astimezone(pytz.utc)
        codigos_de_hoje = Codigo.query.filter(Codigo.criado_em >= inicio_do_dia_utc).order_by(Codigo.criado_em.desc()).all()
        alunos = Aluno.query.order_by(Aluno.nome_completo).all()
        
        alunos_com_status = []
        hoje = datetime.now(FUSO_HORARIO_BRASILIA).date()
        for aluno in alunos:
            presenca_hoje = Presenca.query.filter_by(aluno_id=aluno.id, data=hoje).first()
            status = "Presente" if presenca_hoje else "Ausente"
            alunos_com_status.append({'aluno': aluno, 'status': status})
        return render_template('admin_dashboard.html', 
                               alunos=alunos, 
                               codigo_ativo_existente=codigo_ativo_existente, 
                               codigos_de_hoje=codigos_de_hoje,
                               alunos_com_status=alunos_com_status)
    except Exception as e:
        flash(f'Ocorreu um erro ao carregar o painel: {e}', 'danger')
        return render_template('admin_dashboard.html', alunos=[], codigo_ativo_existente=False, codigos_de_hoje=[], alunos_com_status=[])

@app.route('/admin/gerar_codigo', methods=['POST'])
def gerar_codigo():
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'admin': return redirect(url_for('login'))
    try:
        agora_utc = datetime.utcnow()
        if Codigo.query.filter(Codigo.expira_em > agora_utc).first():
            flash('Aguarde o código atual expirar para gerar um novo.', 'warning')
            return redirect(url_for('painel_admin', _anchor='gerador'))
        expiracao = agora_utc + timedelta(minutes=15)
        novo_codigo_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        db.session.add(Codigo(codigo=novo_codigo_str, criado_em=agora_utc, expira_em=expiracao))
        hoje = datetime.now(FUSO_HORARIO_BRASILIA).date()
        alunos_sem_presenca = Aluno.query.filter(~Aluno.presencas.any(Presenca.data == hoje)).all()
        for aluno in alunos_sem_presenca:
            if not Falta.query.filter_by(aluno_id=aluno.id, data=hoje).first():
                db.session.add(Falta(aluno_id=aluno.id, data=hoje))
        db.session.commit()
        flash(f'Novo código gerado: {novo_codigo_str} (válido por 15 minutos)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao gerar o código: {e}', 'danger')
    return redirect(url_for('painel_admin', _anchor='gerador'))
    
@app.route('/admin/cadastrar_aluno', methods=['POST'])
def cadastrar_aluno():
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'admin': return redirect(url_for('login'))
    try:
        cpf = request.form.get('cpf', '').strip()
        if not cpf.isdigit():
            flash('O CPF deve conter apenas números.', 'danger')
            return redirect(url_for('painel_admin', _anchor='cadastro'))
        idade = request.form.get('idade')
        if idade and int(idade) < 0:
            flash('A idade não pode ser um número negativo.', 'danger')
            return redirect(url_for('painel_admin', _anchor='cadastro'))

        campos_obrigatorios = {'Nome Completo': request.form.get('nome_completo'), 'Usuário': request.form.get('nome_usuario'), 'Senha': request.form.get('senha'), 'E-mail': request.form.get('email'), 'CPF': cpf}
        for nome_campo, valor_campo in campos_obrigatorios.items():
            if not valor_campo or not valor_campo.strip():
                flash(f'O campo "{nome_campo}" é obrigatório.', 'danger')
                return redirect(url_for('painel_admin', _anchor='cadastro'))
        if Aluno.query.filter_by(cpf=cpf).first():
            flash('Erro: O CPF informado já existe.', 'danger')
            return redirect(url_for('painel_admin', _anchor='cadastro'))
        if Aluno.query.filter_by(email=campos_obrigatorios['E-mail'].strip()).first():
            flash('Erro: O E-mail informado já existe.', 'danger')
            return redirect(url_for('painel_admin', _anchor='cadastro'))
        if Aluno.query.filter_by(nome_usuario=campos_obrigatorios['Usuário'].strip()).first():
            flash('Erro: O Nome de Usuário já existe.', 'danger')
            return redirect(url_for('painel_admin', _anchor='cadastro'))
        
        novo_aluno = Aluno(
            nome_completo=campos_obrigatorios['Nome Completo'].strip(), nome_usuario=campos_obrigatorios['Usuário'].strip(), senha=campos_obrigatorios['Senha'], email=campos_obrigatorios['E-mail'].strip(), cpf=campos_obrigatorios['CPF'],
            idade=int(idade) if idade else None, telefone=request.form.get('telefone', '').strip(), naturalidade=request.form.get('naturalidade', '').strip(),
            curso=request.form.get('curso', '').strip(), nivel=request.form.get('nivel', '').strip(), instituicao=request.form.get('instituicao', '').strip()
        )
        db.session.add(novo_aluno)
        db.session.commit()
        flash('Aluno cadastrado com sucesso!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Ocorreu um erro de integridade. Verifique se os dados já não existem.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro inesperado: {e}', 'danger')
    return redirect(url_for('painel_admin', _anchor='cadastro'))

@app.route('/admin/aluno/<int:aluno_id>/editar', methods=['GET', 'POST'])
def editar_aluno(aluno_id):
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'admin': return redirect(url_for('login'))
    aluno = Aluno.query.get_or_404(aluno_id)
    if request.method == 'POST':
        try:
            aluno.nome_completo = request.form.get('nome_completo')
            aluno.nome_usuario = request.form.get('nome_usuario')
            aluno.email = request.form.get('email')
            aluno.telefone = request.form.get('telefone')
            aluno.cpf = request.form.get('cpf')
            aluno.idade = int(request.form.get('idade')) if request.form.get('idade') else None
            aluno.naturalidade = request.form.get('naturalidade')
            aluno.curso = request.form.get('curso')
            aluno.nivel = request.form.get('nivel')
            aluno.instituicao = request.form.get('instituicao')
            if request.form.get('senha'):
                aluno.senha = request.form.get('senha')
            db.session.commit()
            flash('Dados do aluno atualizados com sucesso!', 'success')
            return redirect(url_for('painel_admin'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ocorreu um erro ao atualizar: {e}', 'danger')
    return render_template('editar_aluno.html', aluno=aluno)

@app.route('/admin/aluno/<int:aluno_id>/deletar', methods=['POST'])
def deletar_aluno(aluno_id):
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'admin': return redirect(url_for('login'))
    try:
        aluno = Aluno.query.get_or_404(aluno_id)
        db.session.delete(aluno)
        db.session.commit()
        flash('Aluno deletado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao deletar o aluno: {e}', 'danger')
    return redirect(url_for('painel_admin'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)