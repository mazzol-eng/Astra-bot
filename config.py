"""Configuração exclusiva do servidor. Nunca publique .env no site."""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str
    admin_chat_id: int | None
    use_webhook: bool
    webhook_url: str
    webhook_secret: str
    port: int


def load_settings() -> Settings:
    load_dotenv(Path(__file__).with_name('.env'), override=False)
    token = os.getenv('BOT_TOKEN', '').strip()
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token):
        raise ValueError('Configure BOT_TOKEN no .env com o token do BotFather.')
    admin = os.getenv('ADMIN_CHAT_ID', '').strip()
    webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
    url = os.getenv('WEBHOOK_URL', '').strip().rstrip('/')
    secret = os.getenv('WEBHOOK_SECRET', '').strip()
    port = int(os.getenv('PORT', '8080'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT precisa estar entre 1 e 65535.')
    if webhook:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('WEBHOOK_URL deve ser a origem HTTPS pública, sem caminho ou credenciais.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret):
            raise ValueError('WEBHOOK_SECRET deve ter 32–256 letras, números, _ ou -.')
    return Settings(token, int(admin) if admin else None, webhook, url, secret, port)
