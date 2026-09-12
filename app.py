import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io
import re
import urllib.request
import streamlit as st

# ReportLab para geração do PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES DE VALIDAÇÃO E FORMATAÇÃO
# -----------------------------------------------------------------------------
def validar_cpf(cpf_raw: str) -> bool:
    cpf = re.sub(r'\D', '', str(cpf_raw))
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        val = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digit = ((val * 10) % 11) % 10
        if str(digit) != cpf[i]:
            return False
    return True

def validar_cnpj(cnpj_raw: str) -> bool:
    cnpj = re.sub(r'\D', '', str(cnpj_raw))
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma_1 = sum(int(cnpj[i]) * pesos_1[i] for i in range(12))
    resto_1 = soma_1 % 11
    digito_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int(cnpj[12]) != digito_1:
        return False
    soma_2 = sum(int(cnpj[i]) * pesos_2[i] for i in range(13))
    resto_2 = soma_2 % 11
    digito_2 = 0 if resto_2 < 2 else 11 - resto_2
    return int(cnpj[13]) == digito_2

def formatar_cpf(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else val

def formatar_cnpj(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else val

def formatar_telefone(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    elif len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return val

def formatar_data(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    return f"{d[:2]}/{d[2:4]}/{d[4:]}" if len(d) == 8 else val

def formatar_moeda(val: str) -> str:
    if not val:
        return ""
    clean = str(val).upper().replace("R$", "").strip()
    clean_digits = re.sub(r'[^\d,.]', '', clean)
    if ',' in clean_digits:
        clean_digits = clean_digits.replace('.', '').replace(',', '.')
    else:
        if clean_digits.count('.') > 1:
            clean_digits = clean_digits.replace('.', '')
        elif clean_digits.count('.') == 1 and len(clean_digits.split('.')[1]) != 2:
            clean_digits = clean_digits.replace('.', '')
    try:
        num = float(clean_digits)
        return f"R$ {num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return val

# -----------------------------------------------------------------------------
# GERADOR DE PDF DA FICHA CADASTRAL DO PROPRIETÁRIO
# -----------------------------------------------------------------------------
def gerar_pdf_ficha_proprietario(dados: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=13, textColor=colors.HexColor("#C4001A"), spaceAfter=8)
    style_section = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor("#2B2B2B"), spaceBefore=10, spaceAfter=5)
    style_body = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#333333"))
    style_bold = ParagraphStyle('Bold', parent=style_body, fontName='Helvetica-Bold')

    elements = []

    try:
        logo_url = "https://raw.githubusercontent.com/mrcimoveis-coder/intranet/main/logo.jpeg"
        logo_data = urllib.request.urlopen(logo_url).read()
        elements.append(Image(io.BytesIO(logo_data), width=140, height=48, hAlign='LEFT'))
        elements.append(Spacer(1, 8))
    except Exception:
        pass

    elements.append(Paragraph(f"<b>FICHA CADASTRAL DO PROPRIETÁRIO ({dados['tipo_pessoa'].upper()})</b>", style_title))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#C4001A"), spaceAfter=12))

    def montar_tabela(dados_sec):
        data_table = []
        for k, v in dados_sec.items():
            if v:
                data_table.append([Paragraph(f"<b>{k}:</b>", style_bold), Paragraph(str(v), style_body)])
        if not data_table:
            return Spacer(1, 1)
        t = Table(data_table, colWidths=[160, 360])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    # 1. Identificação do Proprietário
    if dados["tipo_pessoa"] == "Pessoa Física":
        sec1 = {
            "Tipo de Titular": "Pessoa Física",
            "Nome Completo": dados["nome_completo"],
            "CPF": dados["cpf_cnpj"],
            "RG": f"{dados['rg']} (Órgão: {dados['rg_orgao']})",
            "Data de Nascimento": dados["dt_nascimento"],
            "Estado Civil": dados["estado_civil"],
            "E-mail": dados["email_contato"],
            "Telefone Celular": dados["celular"],
            "Endereço Residencial": dados["endereco_titular"]
        }
    else:
        sec1 = {
            "Tipo de Titular": "Pessoa Jurídica",
            "Razão Social": dados["nome_completo"],
            "Nome Fantasia": dados.get("nome_fantasia"),
            "CNPJ": dados["cpf_cnpj"],
            "Inscrição Estadual": dados.get("insc_estadual"),
            "Data de Fundação": dados["dt_nascimento"],
            "E-mail Corporativo": dados["email_contato"],
            "Telefone Comercial": dados["celular"],
            "Endereço da Sede": dados["endereco_titular"],
            "Sócio-Administrador": dados.get("socio_nome"),
            "CPF do Sócio": dados.get("socio_cpf"),
            "RG do Sócio": f"{dados.get('socio_rg')} (Órgão: {dados.get('socio_rg_orgao')})",
            "Cargo na Empresa": dados.get("socio_cargo")
        }

    elements.append(Paragraph("1. Identificação do Proprietário (Locador)", style_section))
    elements.append(montar_tabela(sec1))
    elements.append(Spacer(1, 8))

    # 2. Cônjuge (se PF e casado/união)
    if dados.get("conj_nome"):
        sec2 = {
            "Nome do Cônjuge": dados["conj_nome"],
            "CPF do Cônjuge": dados["conj_cpf"],
            "RG do Cônjuge": f"{dados['conj_rg']} (Órgão: {dados['conj_rg_orgao']})",
            "Celular do Cônjuge": dados.get("conj_celular"),
            "E-mail do Cônjuge": dados.get("conj_email")
        }
        elements.append(Paragraph("2. Dados do Cônjuge / Co-proprietário", style_section))
        elements.append(montar_tabela(sec2))
        elements.append(Spacer(1, 8))

    # 3. Dados do Imóvel a Captação
    sec3 = {
        "Finalidade da Captação": dados["finalidade_captacao"],
        "Endereço do Imóvel": dados["endereco_imovel"],
        "Valor Pretendido Aluguel": dados.get("valor_aluguel"),
        "Valor Pretendido Venda": dados.get("valor_venda"),
        "Valor do Condomínio": dados.get("valor_condominio"),
        "Valor do IPTU Mensal/Anual": dados.get("valor_iptu"),
        "Matrícula RGI / Cartório": dados.get("matricula_rgi"),
        "Inscrição IPTU": dados.get("inscricao_iptu"),
        "Área Privativa (m²)": dados.get("area_m2"),
        "Características": f"{dados.get('qtd_quartos')} quarto(s) | {dados.get('qtd_vagas')} vaga(s)",
        "Situação Atual": dados.get("situacao_imovel"),
        "Localização das Chaves": dados.get("chaves_local")
    }
    elements.append(Paragraph("3. Informações do Imóvel Captado", style_section))
    elements.append(montar_tabela(sec3))
    elements.append(Spacer(1, 8))

    # 4. Dados Bancários para Repasse Financeiro
    sec4 = {
        "Banco": dados["banco"],
        "Agência": dados["agencia"],
        "Conta Corrente/Poupança": dados["conta"],
        "Tipo de Conta": dados["tipo_conta"],
        "Nome do Titular da Conta": dados["titular_conta"],
        "CPF/CNPJ do Titular da Conta": dados["cpf_cnpj_conta"],
        "Chave PIX": dados.get("chave_pix")
    }
    elements.append(Paragraph("4. Dados Bancários para Repasse Financeiro", style_section))
    elements.append(montar_tabela(sec4))
    elements.append(Spacer(1, 8))

    # 5. Observações
    sec5 = {
        "Observações Adicionais": dados["observacoes"]
    }
    elements.append(Paragraph("5. Observações", style_section))
    elements.append(montar_tabela(sec5))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# INTERFACE STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Ficha Cadastral do Proprietário | MRC Imóveis", page_icon="🔑", layout="centered")

try:
    st.image("https://raw.githubusercontent.com/mrcimoveis-coder/intranet/main/logo.jpeg", width=260)
except Exception:
    pass

st.title("🔑 Ficha Cadastral do Proprietário")
st.write("Preencha os dados abaixo para disponibilizar seu imóvel para locação ou venda com a MRC Imóveis.")

# 1. Identificação do Proprietário
st.subheader("1. Identificação do Proprietário")
tipo_pessoa = st.radio("O proprietário do imóvel é: *", ["Pessoa Física", "Pessoa Jurídica"], horizontal=True)

socio_nome, socio_cpf_raw, socio_rg, socio_rg_orgao, socio_cargo = "", "", "", "", ""
conj_nome, conj_cpf_raw, conj_rg, conj_rg_orgao, conj_celular_raw, conj_email = "", "", "", "", "", ""

if tipo_pessoa == "Pessoa Física":
    col1, col2 = st.columns(2)
    with col1:
        nome_completo = st.text_input("Nome Completo do Titular *")
        cpf_cnpj_raw = st.text_input("CPF *", placeholder="000.000.000-00")
        rg = st.text_input("Número do RG *")
        rg_orgao = st.text_input("Órgão Emissor / UF *", placeholder="Ex: SSP/DF")
    with col2:
        dt_nasc_raw = st.text_input("Data de Nascimento *", placeholder="DD/MM/AAAA")
        celular_raw = st.text_input("Telefone Celular (WhatsApp) *", placeholder="(61) 90000-0000")
        email_contato = st.text_input("E-mail Principal *", placeholder="exemplo@email.com")
        estado_civil = st.selectbox("Estado Civil *", ["Solteiro(a)", "Casado(a)", "União Estável", "Divorciado(a)", "Viúvo(a)"])

    endereco_titular = st.text_input("Endereço Residencial Atual Completo (com CEP) *")

    if estado_civil in ["Casado(a)", "União Estável"]:
        st.markdown("---")
        st.subheader("1.1. Dados do Cônjuge / Co-proprietário")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            conj_nome = st.text_input("Nome Completo do Cônjuge *")
            conj_cpf_raw = st.text_input("CPF do Cônjuge *", placeholder="000.000.000-00")
            conj_rg = st.text_input("RG do Cônjuge *")
            conj_rg_orgao = st.text_input("Órgão Emissor / UF Cônjuge *", placeholder="Ex: SSP/DF")
        with col_c2:
            conj_celular_raw = st.text_input("Celular do Cônjuge *", placeholder="(61) 90000-0000")
            conj_email = st.text_input("E-mail do Cônjuge", placeholder="conjuge@email.com")

else:
    col_pj1, col_pj2 = st.columns(2)
    with col_pj1:
        nome_completo = st.text_input("Razão Social *")
        nome_fantasia = st.text_input("Nome Fantasia")
        cpf_cnpj_raw = st.text_input("CNPJ *", placeholder="00.000.000/0001-00")
        insc_estadual = st.text_input("Inscrição Estadual (ou Isento)")
    with col_pj2:
        dt_nasc_raw = st.text_input("Data de Fundação *", placeholder="DD/MM/AAAA")
        celular_raw = st.text_input("Telefone Comercial *", placeholder="(61) 3000-0000")
        email_contato = st.text_input("E-mail Corporativo *", placeholder="contato@empresa.com.br")
        estado_civil = "N/A (Pessoa Jurídica)"

    endereco_titular = st.text_input("Endereço Completo da Sede (com CEP) *")

    st.markdown("---")
    st.subheader("1.1. Dados do Sócio-Administrador / Representante Legal")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        socio_nome = st.text_input("Nome Completo do Sócio Responsável *")
        socio_cpf_raw = st.text_input("CPF do Sócio Responsável *", placeholder="000.000.000-00")
        socio_rg = st.text_input("RG do Sócio *")
    with col_s2:
        socio_rg_orgao = st.text_input("Órgão Emissor / UF do Sócio *", placeholder="Ex: SSP/DF")
        socio_cargo = st.text_input("Cargo / Função na Empresa *", placeholder="Ex: Sócio-Administrador, Diretor")

# 2. Dados do Imóvel
st.markdown("---")
st.subheader("2. Dados do Imóvel para Captação")
finalidade_captacao = st.selectbox("Deseja disponibilizar o imóvel para: *", ["Locação", "Venda", "Locação e Venda"])

endereco_imovel = st.text_input("Endereço Completo do Imóvel a ser Trabalhado (com CEP) *")

col_i1, col_i2 = st.columns(2)
with col_i1:
    valor_aluguel_raw = ""
    if "Locação" in finalidade_captacao:
        valor_aluguel_raw = st.text_input("Valor Pretendido de Aluguel (R$) *", placeholder="Ex: 3500")
    
    valor_venda_raw = ""
    if "Venda" in finalidade_captacao:
        valor_venda_raw = st.text_input("Valor Pretendido de Venda (R$) *", placeholder="Ex: 850000")

    valor_condominio_raw = st.text_input("Valor Atual do Condomínio (R$)", placeholder="Ex: 650")
    valor_iptu_raw = st.text_input("Valor do IPTU (R$)", placeholder="Ex: 1200")
with col_i2:
    matricula_rgi = st.text_input("Número da Matrícula e Cartório de Imóveis (RGI) *", placeholder="Ex: Matrícula 12.345 - 1º RGI/DF")
    inscricao_iptu = st.text_input("Inscrição Cadastral IPTU / GDF *")
    area_m2 = st.text_input("Área Privativa Útil (m²)", placeholder="Ex: 85")

col_ic1, col_ic2 = st.columns(2)
with col_ic1:
    qtd_quartos = st.text_input("Quantidade de Quartos / Suítes", placeholder="Ex: 3 quartos (1 suíte)")
    qtd_vagas = st.text_input("Vagas de Garagem", placeholder="Ex: 2 vagas cobertas")
with col_ic2:
    situacao_imovel = st.selectbox("Situação Atual do Imóvel *", ["Desocupado", "Alugado", "Habitado pelo Proprietário"])
    chaves_local = st.text_input("Localização das Chaves / Acesso *", placeholder="Ex: Na portaria, com o proprietário, imobiliária...")

# 3. Dados Bancários para Repasse
st.markdown("---")
st.subheader("3. Dados Bancários para Repasse Financeiro")
st.caption("Conta bancária onde a MRC Imóveis depositará os valores de aluguéis ou vendas.")

col_b1, col_b2 = st.columns(2)
with col_b1:
    banco = st.text_input("Nome ou Número do Banco *", placeholder="Ex: Banco do Brasil (001)")
    agencia = st.text_input("Número da Agência (com dígito) *", placeholder="Ex: 1234-5")
    conta = st.text_input("Número da Conta (com dígito) *", placeholder="Ex: 98765-4")
with col_b2:
    tipo_conta = st.selectbox("Tipo de Conta *", ["Conta Corrente", "Conta Poupança", "Conta Pagamento / Digital"])
    titular_conta = st.text_input("Nome do Titular da Conta *", placeholder="Nome completo ou Razão Social")
    cpf_cnpj_conta = st.text_input("CPF ou CNPJ do Titular da Conta *", placeholder="000.000.000-00 ou 00.000.000/0001-00")
    chave_pix = st.text_input("Chave PIX (opcional)", placeholder="CPF/CNPJ, E-mail, Celular ou Aleatória")

# 4. Envio de Documentos
st.markdown("---")
st.subheader("4. Envio de Documentos (Anexos)")
st.info("Formatos aceitos: PDF, JPG, PNG. Você pode selecionar múltiplos arquivos em cada campo.")

doc_id = st.file_uploader("1. Documento de Identificação do Proprietário / Sócios (RG/CPF/CNH ou Contrato Social) *", accept_multiple_files=True)
doc_matricula = st.file_uploader("2. Certidão de Matrícula Atualizada do Imóvel (RGI) *", accept_multiple_files=True)
doc_comprovante_res = st.file_uploader("3. Comprovante de Residência Atual do Proprietário *", accept_multiple_files=True)
doc_iptu = st.file_uploader("4. Cópia do Espelho do IPTU *", accept_multiple_files=True)
doc_condominio = st.file_uploader("5. Último Boleto do Condomínio", accept_multiple_files=True)

observacoes = st.text_area("Observações Adicionais")
aceito = st.checkbox("Declaro que sou o legítimo proprietário ou representante legal do imóvel e autorizo a captação pela MRC Imóveis. *")

btn_enviar = st.button("🚀 Enviar Ficha do Proprietário", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# PROCESSAMENTO DO ENVIO
# -----------------------------------------------------------------------------
if btn_enviar:
    cpf_cnpj = formatar_cnpj(cpf_cnpj_raw) if tipo_pessoa == "Pessoa Jurídica" else formatar_cpf(cpf_cnpj_raw)
    celular = formatar_telefone(celular_raw)
    dt_nascimento = formatar_data(dt_nasc_raw)
    
    valor_aluguel = formatar_moeda(valor_aluguel_raw)
    valor_venda = formatar_moeda(valor_venda_raw)
    valor_condominio = formatar_moeda(valor_condominio_raw)
    valor_iptu = formatar_moeda(valor_iptu_raw)

    conj_cpf = formatar_cpf(conj_cpf_raw) if conj_cpf_raw else ""
    conj_celular = formatar_telefone(conj_celular_raw) if conj_celular_raw else ""
    socio_cpf = formatar_cpf(socio_cpf_raw) if socio_cpf_raw else ""

    erros = []
    if not aceito:
        erros.append("Você precisa marcar a caixa de declaração autorizando a captação.")
    if not nome_completo or not cpf_cnpj_raw or not email_contato or not celular_raw or not endereco_titular or not endereco_imovel or not matricula_rgi:
        erros.append("Preencha todos os campos obrigatórios (*) da identificação e do imóvel.")

    if tipo_pessoa == "Pessoa Física":
        if not validar_cpf(cpf_raw=cpf_cnpj_raw):
            erros.append("O CPF do proprietário é inválido.")
        if estado_civil in ["Casado(a)", "União Estável"] and (not conj_nome or not conj_cpf_raw or not validar_cpf(conj_cpf_raw)):
            erros.append("Preencha os dados e CPF válido do cônjuge.")
    else:
        if not validar_cnpj(cnpj_raw=cpf_cnpj_raw):
            erros.append("O CNPJ da empresa proprietária é inválido.")
        if not socio_nome or not socio_cpf_raw or not validar_cpf(socio_cpf_raw):
            erros.append("Preencha os dados e CPF válido do Sócio-Administrador.")

    if not banco or not agencia or not conta or not titular_conta or not cpf_cnpj_conta:
        erros.append("Preencha todos os dados bancários obrigatórios para o repasse financeiro.")

    if erros:
        for err in erros:
            st.error(f"⚠️ {err}")
    else:
        with st.spinner("Gerando Ficha do Proprietário em PDF e enviando e-mail... Aguarde..."):
            try:
                dados_form = {
                    "tipo_pessoa": tipo_pessoa, "nome_completo": nome_completo, "nome_fantasia": nome_fantasia if tipo_pessoa == "Pessoa Jurídica" else "",
                    "cpf_cnpj": cpf_cnpj, "rg": rg if tipo_pessoa == "Pessoa Física" else "", "rg_orgao": rg_orgao if tipo_pessoa == "Pessoa Física" else "",
                    "insc_estadual": insc_estadual if tipo_pessoa == "Pessoa Jurídica" else "", "dt_nascimento": dt_nascimento,
                    "estado_civil": estado_civil, "email_contato": email_contato, "celular": celular, "endereco_titular": endereco_titular,
                    "socio_nome": socio_nome, "socio_cpf": socio_cpf, "socio_rg": socio_rg, "socio_rg_orgao": socio_rg_orgao, "socio_cargo": socio_cargo,
                    "conj_nome": conj_nome, "conj_cpf": conj_cpf, "conj_rg": conj_rg, "conj_rg_orgao": conj_rg_orgao, "conj_celular": conj_celular, "conj_email": conj_email,
                    "finalidade_captacao": finalidade_captacao, "endereco_imovel": endereco_imovel, "valor_aluguel": valor_aluguel, "valor_venda": valor_venda,
                    "valor_condominio": valor_condominio, "valor_iptu": valor_iptu, "matricula_rgi": matricula_rgi, "inscricao_iptu": inscricao_iptu,
                    "area_m2": area_m2, "qtd_quartos": qtd_quartos, "qtd_vagas": qtd_vagas, "situacao_imovel": situacao_imovel, "chaves_local": chaves_local,
                    "banco": banco, "agencia": agencia, "conta": conta, "tipo_conta": tipo_conta, "titular_conta": titular_conta, "cpf_cnpj_conta": cpf_cnpj_conta, "chave_pix": chave_pix,
                    "observacoes": observacoes
                }

                pdf_bytes = gerar_pdf_ficha_proprietario(dados_form)

                smtp_server = st.secrets["smtp"]["server"]
                smtp_port = st.secrets["smtp"]["port"]
                sender_email = st.secrets["smtp"]["email"]
                sender_password = st.secrets["smtp"]["password"]
                receiver_email = "aluguel@mrcimoveis.com.br"

                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = receiver_email
                msg['Subject'] = f"NOVA CAPTAÇÃO PROPRIETÁRIO [{tipo_pessoa.upper()}] - {nome_completo}"

                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; color: #333333; background-color: #F4F6F8; padding: 20px;">
                    <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border-top: 5px solid #C4001A; padding: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                        <h2 style="color: #C4001A; margin-top: 0;">Nova Captação de Imóvel Recebida — MRC Imóveis</h2>
                        <p><strong>Proprietário:</strong> {nome_completo} ({cpf_cnpj})</p>
                        <p><strong>Tipo:</strong> {tipo_pessoa}</p>
                        <p><strong>Finalidade:</strong> {finalidade_captacao}</p>
                        <p><strong>Endereço do Imóvel:</strong> {endereco_imovel}</p>
                        <p><strong>E-mail:</strong> {email_contato} | <strong>Telefone:</strong> {celular}</p>
                        <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                        <p style="color: #6C757D; font-size: 0.9em;">📌 <strong>A Ficha do Proprietário completa e os dados bancários estão anexados em PDF (Ficha_Proprietario.pdf) com os documentos do imóvel.</strong></p>
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(html_body, 'html'))

                part_pdf = MIMEBase('application', 'pdf')
                part_pdf.set_payload(pdf_bytes)
                encoders.encode_base64(part_pdf)
                part_pdf.add_header('Content-Disposition', f'attachment; filename="Ficha_Proprietario_{nome_completo.replace(" ", "_")}.pdf"')
                msg.attach(part_pdf)

                def anexar_uploads(lista_uploads, categoria):
                    if lista_uploads:
                        for upload in lista_uploads:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(upload.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', f'attachment; filename="{categoria}_{upload.name}"')
                            msg.attach(part)

                anexar_uploads(doc_id, "IDENTIFICACAO")
                anexar_uploads(doc_matricula, "MATRICULA_RGI")
                anexar_uploads(doc_comprovante_res, "ENDERECO_PROPRIETARIO")
                anexar_uploads(doc_iptu, "IPTU")
                anexar_uploads(doc_condominio, "CONDOMINIO")

                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
                server.quit()

                st.success("✅ Ficha do Proprietário enviada com sucesso para a MRC Imóveis!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ Erro ao processar o envio: {e}")
