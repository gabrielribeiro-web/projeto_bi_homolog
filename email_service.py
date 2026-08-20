from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import os

# Configurações do Servidor SMTP (Podem ser lidas do st.secrets no Streamlit Cloud)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "seu-email@grupoquerino.com.br")
SMTP_PASS = os.getenv("SMTP_PASS", "sua-senha-smtp")
URL_PORTAL = os.getenv("URL_PORTAL", "https://seu-portal.streamlit.app")

def enviar_email_primeiro_acesso(email_destino, nome_usuario, senha_provisoria):
    """Envia o e-mail de boas-vindas e credenciais temporárias para o cliente."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🔑 Acesso ao Portal de Dashboard. - Grupo Querino"
        msg["From"] = SMTP_USER
        msg["To"] = email_destino

        corpo_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #1e293b; padding: 30px; border-radius: 10px; border-top: 5px solid #84cc16;">
                <h2 style="color: #84cc16;">Bem-vindo ao Portal de Dashboard. do Grupo Querino</h2>
                <p>Olá, <strong>{nome_usuario}</strong>!</p>
                <p>Seu acesso ao nosso portal de indicadores foi liberado com sucesso. Abaixo estão suas credenciais de primeiro acesso:</p>
                
                <div style="background-color: #0f172a; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Link de Acesso:</strong> <a href="{URL_PORTAL}" style="color: #38bdf8;">{URL_PORTAL}</a></p>
                    <p style="margin: 5px 0;"><strong>E-mail:</strong> {email_destino}</p>
                    <p style="margin: 5px 0;"><strong>Senha Provisória:</strong> <code style="background-color: #334155; padding: 3px 6px; border-radius: 4px; color: #84cc16;">{senha_provisoria}</code></p>
                </div>

                <p style="font-size: 13px; color: #94a3b8;">⚠️ <em>No seu primeiro login, o sistema solicitará obrigatoriamente a criação de uma nova senha pessoal e intransferível.</em></p>
                <hr style="border: 0; border-top: 1px solid #334155; margin: 20px 0;">
                <p style="font-size: 12px; color: #64748b; text-align: center;">Grupo Querino — Inteligência em Treinamentos</p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(corpo_html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, email_destino, msg.as_string())
        
        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        return False, f"Falha no disparo do e-mail: {e}"