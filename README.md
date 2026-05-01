# Bot Telegram Multifuncional

Bot Telegram com várias funcionalidades: status de VPS, whois, ping, conversão de moedas, tradução e encurtar URLs.

## 📁 Estrutura de Arquivos

```
├── main.py                 # Arquivo principal (EXECUTAR ESTE)
├── config.py              # Configurações (TOKEN, AUTHORIZED_ID)
├── utils.py               # Funções utilitárias
├── handlers.py            # Handlers de rede (status, whois, ping)
├── converters.py          # Conversões (moedas)
├── tools.py               # Ferramentas (tradução, encurtar URL)
├── button_handler.py      # Handler dos botões inline
├── requirements.txt       # Dependências do projeto
└── README.md             # Este arquivo
```

## 🚀 Como Usar

### 1. Instalação de Dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar o Token
```bash
export BOT_TOKEN="seu_token_aqui"
```

### 3. Executar o Bot
```bash
python main.py
```

## 📋 Funcionalidades

- **📊 Status** - Mostra CPU, RAM e Uptime da VPS
- **🔎 Whois** - Consulta informações de domínios (`/whois exemplo.com`)
- **🌍 Ping** - Faz ping em sites (`/ping_site google.com`)
- **💱 Conversor** - Converte moedas (`/conversor 100 USD BRL`)
- **📋 Unidades** - Converte unidades (`/unidades 100 km mi`)

- **🌐 Traduz** - Traduz textos (`/traduz es Olá mundo`)
- **🔗 Encurtar** - Encurta URLs (`/encurta https://exemplo.com`)

## 🔑 Autorização

O bot só responde para o usuário com ID configurado em `config.py`:
```python
AUTHORIZED_ID = 12345678  # Altere para seu ID
```

## 📝 Exemplo de Uso

```
/start               # Mostra o menu principal
/status              # Mostra status da VPS
/whois google.com    # Consulta whois do google.com
/conversor 100 USD BRL  # Converte 100 USD para BRL
```

## ⚙️ Requisitos

- Python 3.8+
- Token válido do Telegram Bot
- Acesso à internet para APIs externas
