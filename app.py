import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io
import re
import unicodedata
import urllib.request
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image as PILImage, ImageChops
from xml.sax.saxutils import escape

import gspread
from google.oauth2.service_account import Credentials

# ReportLab para geração do PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

LOGO_URL = "https://raw.githubusercontent.com/mrcimoveis-coder/portal-intranet/main/logo.jpeg"

@st.cache_data(ttl=3600)
def obter_logo_bytes():
    """Baixa e recorta as margens brancas da identidade visual atual da MRC."""
    logo_data = urllib.request.urlopen(LOGO_URL, timeout=10).read()
    with PILImage.open(io.BytesIO(logo_data)).convert("RGB") as imagem:
        fundo = PILImage.new("RGB", imagem.size, "white")
        diferenca = ImageChops.difference(imagem, fundo).convert("L")
        limite = diferenca.point(lambda pixel: 255 if pixel > 12 else 0)
        caixa = limite.getbbox()
        if caixa:
            imagem = imagem.crop(caixa)
        saida = io.BytesIO()
        imagem.save(saida, format="PNG", optimize=True)
        return saida.getvalue()

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

def sanitizar_nome_arquivo(nome):
    n = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('utf-8')
    n = re.sub(r'[^a-zA-Z0-9.]', '_', n)
    n = re.sub(r'\.+', '.', n)
    return re.sub(r'_+', '_', n).strip('_')

def ativar_sincronizacao_autopreenchimento():
    """Faz o Streamlit reconhecer valores escolhidos no autofill do navegador."""
    components.html(
        """
        <script>
        (() => {
          const host = window.parent;
          const doc = host.document;
          if (host.__mrcAutofillSyncInstalled) return;
          host.__mrcAutofillSyncInstalled = true;

          const style = doc.createElement("style");
          style.textContent = `
            @keyframes mrcAutofillStarted { from {} to {} }
            input:-webkit-autofill { animation-name: mrcAutofillStarted; animation-duration: 0.01s; }
          `;
          doc.head.appendChild(style);

          const sincronizar = (input) => {
            if (!input || !input.value) return;
            const valor = input.value;
            if (input.dataset.mrcAutofillSincronizado === valor) return;
            input.dataset.mrcAutofillSincronizado = valor;
            const tracker = input._valueTracker;
            if (tracker) tracker.setValue("");
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
          };

          doc.addEventListener("animationstart", (event) => {
            if (event.animationName === "mrcAutofillStarted") {
              host.setTimeout(() => sincronizar(event.target), 50);
            }
          }, true);

          host.setInterval(() => {
            doc.querySelectorAll("input:-webkit-autofill").forEach(sincronizar);
          }, 500);
        })();
        </script>
        """,
        height=0,
        width=0,
    )

# -----------------------------------------------------------------------------
# INTEGRAÇÃO GOOGLE SHEETS COM A CARTEIRA DE IMÓVEIS
# -----------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def salvar_lead_carteira_sheets(dados_lead: list):
    credenciais_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in credenciais_dict:
        credenciais_dict["private_key"] = credenciais_dict["private_key"].replace("\\n", "\n")
    
    credentials = Credentials.from_service_account_info(credenciais_dict, scopes=SCOPES)
    client = gspread.authorize(credentials)
    
    spreadsheet = client.open_by_key("1yJBZZ0nDnJKsf31H6sfG_vve19TJIRfGIZ4ATCKQS7k")
    
    try:
        sheet_leads = spreadsheet.worksheet("Leads_Captacao")
    except Exception:
        sheet_leads = spreadsheet.add_worksheet(title="Leads_Captacao", rows="200", cols="20")
        
    header = [
        "Data_Registro", "Proprietario_Nome", "Proprietario_Telefone", "Proprietario_Email",
        "Endereco_Imovel", "Bairro", "Tipo_Imovel", "Finalidade", "Valor_Pretendido",
        "Valor_Condominio", "Valor_IPTU", "Status", "Chaves_Local", "Observacoes"
    ]
    
    # Garante que a linha 1 seja sempre o cabeçalho oficial
    valores_existentes = sheet_leads.get_all_values()
    if not valores_existentes:
        sheet_leads.append_row(header)
        
    sheet_leads.append_row(dados_lead)

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
        logo_data = obter_logo_bytes()
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

    elements.append(Paragraph("1. Identificação do Proprietário (Locador/Vendedor)", style_section))
    elements.append(montar_tabela(sec1))
    elements.append(Spacer(1, 8))

    # 2. Cônjuge
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

    # 2. Dados do Imóvel
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
        "Características": f"{dados.get('qtd_quartos')} | {dados.get('qtd_vagas')}",
        "Situação Atual": dados.get("situacao_imovel"),
        "Localização das Chaves": dados.get("chaves_local")
    }
    elements.append(Paragraph("2. Informações do Imóvel Captado", style_section))
    elements.append(montar_tabela(sec3))
    elements.append(Spacer(1, 8))

    # 3. Dados Bancários
    chave_pix_str = ""
    if dados.get("chave_pix"):
        chave_pix_str = f"{dados.get('chave_pix')} ({dados.get('tipo_chave_pix')})"

    sec4 = {
        "Banco": dados["banco"],
        "Agência": dados["agencia"],
        "Conta Corrente/Poupança": dados["conta"],
        "Tipo de Conta": dados["tipo_conta"],
        "Nome do Titular da Conta": dados["titular_conta"],
        "CPF/CNPJ do Titular da Conta": dados["cpf_cnpj_conta"],
        "Chave PIX": chave_pix_str
    }
    elements.append(Paragraph("3. Dados Bancários para Repasse Financeiro", style_section))
    elements.append(montar_tabela(sec4))
    elements.append(Spacer(1, 8))

    # 4. Condições comerciais da venda (somente quando houver venda)
    if "Venda" in dados["finalidade_captacao"]:
        prazo_exclusividade = dados.get("prazo_exclusividade") if dados.get("exclusividade_mrc") == "Sim" else "Não se aplica"
        sec_venda = {
            "Exclusividade para a MRC": dados.get("exclusividade_mrc"),
            "Prazo de Exclusividade (dias)": prazo_exclusividade,
            "Percentual de Venda Acordado": dados.get("percentual_venda"),
            "Corretor Responsável pela Captação": dados.get("corretor_captacao"),
        }
        elements.append(Paragraph("4. Condições Comerciais da Venda", style_section))
        elements.append(montar_tabela(sec_venda))
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

def gerar_pdf_autorizacao_venda(dados: dict) -> bytes:
    """Gera a autorização de venda preenchida para assinatura do proprietário."""
    buffer = io.BytesIO()
    vermelho = colors.HexColor("#C90018")
    azul_escuro = colors.HexColor("#17233C")
    cinza = colors.HexColor("#5F6773")
    cinza_claro = colors.HexColor("#F3F5F8")

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=34,
        leftMargin=34,
        topMargin=28,
        bottomMargin=32,
    )

    style_logo = ParagraphStyle("AuthLogo", alignment=1, spaceAfter=2)
    style_title = ParagraphStyle(
        "AuthTitle", fontName="Helvetica-Bold", fontSize=18, leading=21,
        alignment=1, textColor=azul_escuro, spaceAfter=9,
    )
    style_body = ParagraphStyle(
        "AuthBody", fontName="Helvetica", fontSize=8.4, leading=10.7,
        textColor=colors.HexColor("#2D3440"), alignment=4,
    )
    style_small = ParagraphStyle(
        "AuthSmall", parent=style_body, fontSize=7.3, leading=9.1,
    )
    style_section = ParagraphStyle(
        "AuthSection", fontName="Helvetica-Bold", fontSize=10.2, leading=12,
        alignment=1, textColor=azul_escuro, spaceBefore=7, spaceAfter=5,
    )
    style_label = ParagraphStyle(
        "AuthLabel", parent=style_body, fontName="Helvetica-Bold", fontSize=8.1,
        textColor=azul_escuro,
    )

    def texto(valor):
        return escape(str(valor or ""))

    def decorar_pagina(canvas, _doc):
        largura, altura = A4
        canvas.saveState()
        canvas.setFillColor(vermelho)
        canvas.rect(0, altura - 12, largura, 12, stroke=0, fill=1)
        canvas.rect(0, 0, largura, 10, stroke=0, fill=1)
        canvas.setFillColor(cinza)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawCentredString(
            largura / 2,
            16,
            "MRC EMPREENDIMENTOS IMOBILIARIOS E PARTICIPACOES LTDA - CRECI 18.046/DF",
        )
        canvas.restoreState()

    elements = []
    try:
        logo = Image(io.BytesIO(obter_logo_bytes()), width=160, height=50, hAlign="CENTER")
        elements.append(logo)
    except Exception:
        elements.append(Paragraph("<b>MRC IMÓVEIS</b>", style_logo))

    elements.append(Paragraph("AUTORIZAÇÃO DE VENDA", style_title))
    elements.append(HRFlowable(width="100%", thickness=2.2, color=vermelho, spaceAfter=8))
    elements.append(Paragraph(
        "Autorizo a <b>MRC Empreendimentos Imobiliários e Participações Ltda.</b>, "
        "CRECI 18.046/DF, CNPJ 04.184.638/0001-80, com escritório na EQRSW 07/08, "
        "Lote 01, Sala 01, Ed. Monumental Sudoeste, Brasília (DF), a promover a venda "
        "do imóvel abaixo especificado:",
        style_body,
    ))
    elements.append(Spacer(1, 7))

    exclusividade = texto(dados.get("exclusividade_mrc"))
    prazo = texto(dados.get("prazo_exclusividade")) if dados.get("exclusividade_mrc") == "Sim" else "Não se aplica"
    dados_imovel = [
        [Paragraph("ENDEREÇO", style_label), Paragraph(texto(dados.get("endereco_imovel")), style_body)],
        [Paragraph("REGISTRO / MATRÍCULA", style_label), Paragraph(texto(dados.get("matricula_rgi")), style_body)],
        [Paragraph("VALOR DA VENDA", style_label), Paragraph(texto(dados.get("valor_venda")), style_body)],
        [Paragraph("COMISSÃO DE VENDA", style_label), Paragraph(texto(dados.get("percentual_venda")), style_body)],
        [Paragraph("EXCLUSIVIDADE MRC", style_label), Paragraph(exclusividade, style_body)],
        [Paragraph("PRAZO DE EXCLUSIVIDADE", style_label), Paragraph(f"{prazo} dias" if prazo != "Não se aplica" else prazo, style_body)],
        [Paragraph("CORRETOR RESPONSÁVEL", style_label), Paragraph(texto(dados.get("corretor_captacao")), style_body)],
    ]
    tabela_imovel = Table(dados_imovel, colWidths=[150, 377])
    tabela_imovel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cinza_claro),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9DEE7")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9DEE7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(tabela_imovel)

    elements.append(Paragraph("CONDIÇÕES GERAIS", style_section))
    condicoes = [
        "Na venda à vista, a comissão de venda será paga no ato do pagamento integral do valor.",
        "Na venda a prazo, a comissão de venda será paga integralmente no sinal do negócio, desde que o comprador pague no mínimo 10% do valor total da venda.",
        "Caso o proprietário aceite imóvel como forma de pagamento, a comissão será devida da mesma forma e nos valores combinados.",
        "Será devida a comissão à imobiliária se o imóvel for vendido, durante a validade desta autorização, a pessoa que o tenha visitado acompanhada por corretor ou profissional da MRC.",
        "Os custos de publicidade e propaganda dos anúncios contratados pela imobiliária serão de responsabilidade da MRC.",
        "Esta autorização é válida por 90 (noventa) dias. Quando houver exclusividade, prevalecerá o prazo específico informado acima. A autorização poderá ser renovada por iguais períodos, salvo manifestação escrita do proprietário.",
        "A presente autorização pode ser denunciada a qualquer tempo, respeitadas as condições e os negócios já iniciados durante sua vigência.",
        "A imobiliária não está autorizada a receber sinal nem a assinar documentos de venda em nome do proprietário, salvo mediante procuração específica.",
        "As visitas deverão ser previamente agendadas com o proprietário e acompanhadas por corretor ou profissional da MRC.",
    ]
    for indice, condicao in enumerate(condicoes, start=1):
        elements.append(Paragraph(f"<b>{indice}.</b> {condicao}", style_small))
        elements.append(Spacer(1, 1.5))

    elements.append(Paragraph("PROPRIETÁRIO DO IMÓVEL", style_section))
    dados_proprietario = [
        [Paragraph("NOME / RAZÃO SOCIAL", style_label), Paragraph(texto(dados.get("nome_completo")), style_body)],
        [Paragraph("CPF / CNPJ", style_label), Paragraph(texto(dados.get("cpf_cnpj")), style_body)],
        [Paragraph("TELEFONE", style_label), Paragraph(texto(dados.get("celular")), style_body)],
        [Paragraph("E-MAIL", style_label), Paragraph(texto(dados.get("email_contato")), style_body)],
    ]
    tabela_proprietario = Table(dados_proprietario, colWidths=[150, 377])
    tabela_proprietario.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, colors.HexColor("#C6CCD6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(tabela_proprietario)
    elements.append(Spacer(1, 7))
    elements.append(Paragraph("Brasília (DF), ______ de ________________________ de __________.", style_section))
    elements.append(Spacer(1, 16))
    assinatura = Table([
        ["______________________________________________"],
        [Paragraph("<b>ASSINATURA DO PROPRIETÁRIO</b>", style_section)],
    ], colWidths=[330], hAlign="CENTER")
    assinatura.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    elements.append(assinatura)

    doc.build(elements, onFirstPage=decorar_pagina, onLaterPages=decorar_pagina)
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# INTERFACE STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Ficha Cadastral do Proprietário | MRC Imóveis", page_icon="🔑", layout="centered")
ativar_sincronizacao_autopreenchimento()

if "enviado_sucesso" not in st.session_state:
    st.session_state.enviado_sucesso = False

if st.session_state.enviado_sucesso:
    st.balloons()
    try:
        st.image(obter_logo_bytes(), width=260)
    except Exception:
        pass
    
    st.success("✅ **Ficha do Proprietário e Documentos Enviados com Sucesso!**")
    st.markdown("""
    ### Obrigado por disponibilizar seu imóvel com a **MRC Imóveis**! 🎉
    
    Sua ficha cadastral e os documentos do imóvel foram encaminhados com sucesso para o nosso setor comercial e de captação.
    
    **O que acontece agora?**
    * Nossa equipe analisará os dados do imóvel e a documentação enviada.
    * Um de nossos gestores entrará em contato em breve para dar início à divulgação e agendamento de fotos/visitas.
    
    ---
    📬 **Contatos Úteis:**
    * **E-mail:** aluguel@mrcimoveis.com.br / comercial@mrcimoveis.com.br
    """)
    st.markdown("---")
    if st.button("🔄 Cadastrar outro imóvel"):
        st.session_state.enviado_sucesso = False
        st.rerun()
    st.stop()

# FORMULÁRIO PADRÃO
try:
    st.image(obter_logo_bytes(), width=260)
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

col_b3, col_b4 = st.columns(2)
with col_b3:
    tipo_chave_pix = st.selectbox("Tipo de Chave PIX", ["Nenhuma / Não informar", "CPF/CNPJ", "Celular", "E-mail", "Chave Aleatória / Outra"])
with col_b4:
    chave_pix = st.text_input("Chave PIX", placeholder="Digite a chave PIX escolhida...")

# 4. Condições comerciais da venda
exclusividade_mrc, prazo_exclusividade, percentual_venda, corretor_captacao = "", "", "", ""
if "Venda" in finalidade_captacao:
    st.markdown("---")
    st.subheader("4. Condições Comerciais da Venda")
    exclusividade_mrc = st.radio(
        "O imóvel está sendo dado com exclusividade para a MRC? *",
        ["Sim", "Não"],
        horizontal=True,
        index=None,
    )
    if exclusividade_mrc == "Sim":
        prazo_exclusividade = st.text_input(
            "Prazo de exclusividade (em dias) *",
            placeholder="Ex: 90",
        )
    percentual_venda = st.text_input(
        "Percentual de venda acordado *",
        placeholder="Ex: 5%",
    )
    corretor_captacao = st.text_input(
        "Corretor responsável pela captação *",
        placeholder="Nome do corretor",
    )

# 5. Envio de Documentos
st.markdown("---")
st.subheader("5. Envio de Documentos (Anexos Opcionais)")
st.info("Os anexos não são obrigatórios. Estes campos aceitam PDF, JPG, JPEG, PNG, arquivos do Word, Excel e outros formatos de documentos.")
st.warning("⚠️ **Atenção para enviar vários arquivos:** Selecione todos de uma só vez.")

doc_id = None
doc_contrato = None
doc_cnpj = None

if tipo_pessoa == "Pessoa Física":
    doc_id = st.file_uploader("1. Documento de Identificação do Proprietário (e Cônjuge)", accept_multiple_files=True)
else:
    doc_id = st.file_uploader("1. Documento de Identificação do Sócio-Administrador", accept_multiple_files=True)
    doc_contrato = st.file_uploader("1.1. Contrato Social / Requerimento de Empresário", accept_multiple_files=True)
    doc_cnpj = st.file_uploader("1.2. Cartão do CNPJ da Empresa", accept_multiple_files=True)

doc_matricula = st.file_uploader("2. Certidão de Matrícula Atualizada do Imóvel (RGI)", accept_multiple_files=True)
doc_comprovante_res = st.file_uploader("3. Comprovante de Residência Atual / Sede", accept_multiple_files=True)
doc_iptu = st.file_uploader("4. Cópia do Espelho do IPTU", accept_multiple_files=True)

doc_condominio = st.file_uploader("5. Último Boleto do Condomínio", accept_multiple_files=True)
doc_luz = st.file_uploader("6. Última Conta de Luz", accept_multiple_files=True)
doc_agua = st.file_uploader("7. Última Conta de Água", accept_multiple_files=True)
doc_gas = st.file_uploader("8. Última Conta de Gás", accept_multiple_files=True)
doc_outros = st.file_uploader("9. Outros documentos", accept_multiple_files=True)

observacoes = st.text_area("Observações Adicionais")
aceito = st.checkbox("Declaro que sou o legítimo proprietário ou representante legal e autorizo a captação pela MRC Imóveis. *")

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
    
    if not nome_completo or not cpf_cnpj_raw or not email_contato or not celular_raw or not endereco_titular or not endereco_imovel or not matricula_rgi or not inscricao_iptu:
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

    if "Venda" in finalidade_captacao:
        if not exclusividade_mrc:
            erros.append("Informe se o imóvel será trabalhado com exclusividade pela MRC.")
        if exclusividade_mrc == "Sim" and not prazo_exclusividade.strip():
            erros.append("Informe o prazo da exclusividade em dias.")
        if not percentual_venda.strip():
            erros.append("Informe o percentual de venda acordado.")
        if not corretor_captacao.strip():
            erros.append("Informe o corretor responsável pela captação.")

    if erros:
        for err in erros:
            st.error(f"⚠️ {err}")
    else:
        with st.spinner("Gerando Ficha, salvando na Carteira e enviando e-mail... Aguarde..."):
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
                    "banco": banco, "agencia": agencia, "conta": conta, "tipo_conta": tipo_conta, "titular_conta": titular_conta, "cpf_cnpj_conta": cpf_cnpj_conta, 
                    "tipo_chave_pix": tipo_chave_pix, "chave_pix": chave_pix,
                    "exclusividade_mrc": exclusividade_mrc, "prazo_exclusividade": prazo_exclusividade,
                    "percentual_venda": percentual_venda, "corretor_captacao": corretor_captacao,
                    "observacoes": observacoes
                }

                # 1. SALVAR AUTOMATICAMENTE NA PLANILHA DE TRIAGEM DA CARTEIRA
                val_pretendido_str = ""
                if valor_aluguel and valor_venda:
                    val_pretendido_str = f"Aluguel: {valor_aluguel} | Venda: {valor_venda}"
                elif valor_aluguel:
                    val_pretendido_str = valor_aluguel
                elif valor_venda:
                    val_pretendido_str = valor_venda

                linha_lead_carteira = [
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    nome_completo,
                    celular,
                    email_contato,
                    endereco_imovel,
                    "A definir",
                    "Apartamento",
                    finalidade_captacao,
                    val_pretendido_str,
                    valor_condominio,
                    valor_iptu,
                    "Novo Lead",
                    chaves_local,
                    (
                        f"Situação: {situacao_imovel} | Exclusividade MRC: {exclusividade_mrc or 'Não se aplica'}"
                        f" | Prazo: {prazo_exclusividade or 'Não se aplica'} | Percentual venda: {percentual_venda or 'Não se aplica'}"
                        f" | Corretor: {corretor_captacao or 'Não se aplica'} | Obs: {observacoes}"
                    )
                ]
                
                salvar_lead_carteira_sheets(linha_lead_carteira)

                # 2. GERAR PDF E ENVIAR POR E-MAIL
                pdf_bytes = gerar_pdf_ficha_proprietario(dados_form)
                autorizacao_venda_bytes = None
                if "Venda" in finalidade_captacao:
                    autorizacao_venda_bytes = gerar_pdf_autorizacao_venda(dados_form)

                smtp_server = st.secrets["smtp"]["server"]
                smtp_port = st.secrets["smtp"]["port"]
                sender_email = st.secrets["smtp"]["email"]
                sender_password = st.secrets["smtp"]["password"]
                receiver_emails = ["aluguel@mrcimoveis.com.br", "comercial@mrcimoveis.com.br"]

                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = ", ".join(receiver_emails)
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
                        {f'<p><strong>Exclusividade MRC:</strong> {exclusividade_mrc} {f"— {prazo_exclusividade} dias" if exclusividade_mrc == "Sim" else ""}</p><p><strong>Percentual de venda:</strong> {percentual_venda}</p><p><strong>Corretor responsável:</strong> {corretor_captacao}</p>' if "Venda" in finalidade_captacao else ''}
                        <p><strong>E-mail:</strong> {email_contato} | <strong>Telefone:</strong> {celular}</p>
                        <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                        <p style="color: #6C757D; font-size: 0.9em;">📌 <strong>Este imóvel foi cadastrado automaticamente na aba de Triagem da Carteira de Imóveis.</strong></p>
                        {f'<p style="color: #6C757D; font-size: 0.9em;">📎 <strong>A Autorização de Venda preenchida segue anexa e também foi enviada ao proprietário para assinatura.</strong></p>' if autorizacao_venda_bytes else ''}
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(html_body, 'html'))

                part_pdf = MIMEBase('application', 'pdf')
                part_pdf.set_payload(pdf_bytes)
                encoders.encode_base64(part_pdf)
                nome_pdf_seguro = sanitizar_nome_arquivo(f"Ficha_Proprietario_{nome_completo}.pdf")
                part_pdf.add_header('Content-Disposition', 'attachment', filename=nome_pdf_seguro)
                msg.attach(part_pdf)

                nome_autorizacao_seguro = ""
                if autorizacao_venda_bytes:
                    nome_autorizacao_seguro = sanitizar_nome_arquivo(f"Autorizacao_de_Venda_{nome_completo}.pdf")
                    part_autorizacao = MIMEBase('application', 'pdf')
                    part_autorizacao.set_payload(autorizacao_venda_bytes)
                    encoders.encode_base64(part_autorizacao)
                    part_autorizacao.add_header('Content-Disposition', 'attachment', filename=nome_autorizacao_seguro)
                    msg.attach(part_autorizacao)

                def anexar_uploads(lista_uploads, categoria):
                    if lista_uploads:
                        for upload in lista_uploads:
                            upload.seek(0)
                            file_bytes = upload.read()
                            if not file_bytes:
                                continue
                            nome_seguro = sanitizar_nome_arquivo(upload.name)
                            nome_final = f"{categoria}_{nome_seguro}"
                            
                            part = MIMEBase('application', 'octet-stream', name=nome_final)
                            part.set_payload(file_bytes)
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', 'attachment', filename=nome_final)
                            msg.attach(part)

                anexar_uploads(doc_id, "IDENTIFICACAO")
                if tipo_pessoa == "Pessoa Jurídica":
                    anexar_uploads(doc_contrato, "CONTRATO_SOCIAL")
                    anexar_uploads(doc_cnpj, "CARTAO_CNPJ")
                
                anexar_uploads(doc_matricula, "MATRICULA_RGI")
                anexar_uploads(doc_comprovante_res, "ENDERECO_PROPRIETARIO")
                anexar_uploads(doc_iptu, "IPTU")
                anexar_uploads(doc_condominio, "CONDOMINIO")
                anexar_uploads(doc_luz, "CONTA_LUZ")
                anexar_uploads(doc_agua, "CONTA_AGUA")
                anexar_uploads(doc_gas, "CONTA_GAS")
                anexar_uploads(doc_outros, "OUTROS_DOCUMENTOS")

                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_emails, msg.as_string())

                if autorizacao_venda_bytes:
                    msg_cliente = MIMEMultipart()
                    msg_cliente['From'] = sender_email
                    msg_cliente['To'] = email_contato
                    msg_cliente['Reply-To'] = "comercial@mrcimoveis.com.br"
                    msg_cliente['Subject'] = "Autorização de Venda para assinatura - MRC Imóveis"
                    nome_cliente_html = escape(nome_completo)
                    corretor_html = escape(corretor_captacao)
                    html_cliente = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; color: #17233C; background-color: #F3F5F8; padding: 20px;">
                        <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border-top: 5px solid #C90018; padding: 25px;">
                            <h2 style="color: #C90018; margin-top: 0;">Autorização de Venda - MRC Imóveis</h2>
                            <p>Olá, <strong>{nome_cliente_html}</strong>.</p>
                            <p>A Autorização de Venda do imóvel informado em sua ficha cadastral segue preenchida em anexo.</p>
                            <p><strong>Para concluir:</strong></p>
                            <ol>
                                <li>Confira os dados do documento anexo.</li>
                                <li>Assine eletronicamente pelo <a href="https://www.gov.br/governodigital/pt-br/assinatura-eletronica">portal gov.br</a>.</li>
                                <li>Envie o documento assinado para <strong>comercial@mrcimoveis.com.br</strong> ou diretamente ao corretor <strong>{corretor_html}</strong>.</li>
                            </ol>
                            <p>Em caso de dúvida, responda a este e-mail para falar com a equipe da MRC.</p>
                            <p style="color: #5F6773; font-size: 0.9em;">Atenciosamente,<br><strong>MRC Imóveis</strong><br>CRECI 18.046/DF</p>
                        </div>
                    </body>
                    </html>
                    """
                    msg_cliente.attach(MIMEText(html_cliente, 'html'))
                    part_cliente = MIMEBase('application', 'pdf')
                    part_cliente.set_payload(autorizacao_venda_bytes)
                    encoders.encode_base64(part_cliente)
                    part_cliente.add_header('Content-Disposition', 'attachment', filename=nome_autorizacao_seguro)
                    msg_cliente.attach(part_cliente)
                    server.sendmail(sender_email, [email_contato], msg_cliente.as_string())

                server.quit()

                st.session_state.enviado_sucesso = True
                st.rerun()

            except Exception as e:
                st.error(f"❌ Erro ao processar o envio: {e}")
