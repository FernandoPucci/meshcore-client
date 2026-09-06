# MeshCore Monitor

Aplicação Python para monitorar um nó MeshCore Companion via porta serial, exibindo todos os dados recebidos em tempo real no console.

## 📋 Funcionalidades

- **Conexão serial** com nó MeshCore Companion (porta `/dev/ttyUSB0` @ 115200 baud)
- **Informações do dispositivo**: modelo, firmware, configuração de rádio (frequência, SF, BW, CR)
- **Lista de contatos** com nomes, tipos (CONTACT/REPEATER/ROOM), chaves públicas e localização
- **Canais configurados** (ex: canal 0 "Public")
- **Envio de advert** (anúncio de presença) na inicialização
- **Monitoramento em tempo real** de:
  - Mensagens de contato (DMs)
  - Mensagens de **TODOS os canais** (grupo) - não apenas Public
  - Pacotes LoRa brutos (RX_LOG) com RSSI, SNR, tipo de rota, path
  - **Advertisements (anúncios)** com captura automática de dados do anunciante
  - Eventos de sistema (bateria, telemetria, stats, etc.)
- **Armazenamento persistente** de nós conhecidos em `known_nodes.json`
- **Consulta METAR via REDEMET API** - Responde a DMs com `METAR <ICAO>` (ex: `METAR SBRP`) retornando dados meteorológicos formatados
- **Envio de tempo/clima via Open-Meteo API** - Ctrl+F publica no canal #Public: temperatura, umidade, fase da lua, hora e data (máx. 130 chars)
- **Envio automático de tempo/clima (cron)** - Configurável via variáveis de ambiente: envia periodicamente no canal #Public com emoji + descrição em português do tempo e fase da lua

## 🔧 Requisitos

- Python 3.10+
- Biblioteca `meshcore` (SDK oficial Python)
- Permissão de acesso à porta serial (`dialout` group)

## 📦 Instalação

```bash
# Instalar SDK MeshCore
pip install meshcore aiohttp

# Verificar porta serial
ls -la /dev/ttyUSB*
# Deve mostrar /dev/ttyUSB0 (ajuste no código se diferente)

# Adicionar usuário ao grupo dialout (se necessário)
sudo usermod -a -G dialout $USER
# Faça logout/login após isso
```

## ▶️ Execução

```bash
# Executar monitor
python3 meshcore_monitor.py

# Atalhos:
#   Ctrl+A = Enviar advert (anúncio de presença)
#   Ctrl+F = Enviar tempo/clima para canal #Public
#   Ctrl+C = Sair
```

**Nota:** O atalho Ctrl+A funciona apenas quando executado em terminal interativo (TTY).

### Envio Automático de Tempo/Clima (Cron via Variável de Ambiente)

Configure as variáveis abaixo no `.env` para habilitar o envio periódico automático:

```bash
# Habilita envio automático (true/false)
WEATHER_AUTO_SEND_ENABLED=true

# Intervalo em minutos (padrão: 30)
WEATHER_AUTO_SEND_INTERVAL=30

# Índice do canal destino (padrão: 0 = #Public)
WEATHER_AUTO_SEND_CHANNEL=0
```

Ao habilitar, o sistema envia a previsão **imediatamente na inicialização** e depois a cada N minutos configurados. A mensagem inclui emoji + **descrição completa em português** do código do tempo (WMO) e fase da lua.

## 📊 Saída Esperada

### Inicialização
```
🔌 Connecting to MeshCore on /dev/ttyUSB2 @ 115200 (attempt 1/3)...
✅ Connected!

📋 Getting device info...

======================================================================
📋 NODE INFO
======================================================================
  fw ver: 13
  max_contacts: 350
  max_channels: 40
  ble_pin: 0
  fw_build: 14-Aug-2026
  model: Heltec V3
  ver: v1.17.1-d929643
  repeat: False
  path_hash_mode: 1
======================================================================

   Heltec V3 | v1.17.1-d929643
👥 Getting contacts...

======================================================================
👥 CONTACT LIST (8 contacts)
======================================================================
  [CONTACT] Roberto Oliva (e006fc782db2...)  lat=-21.205126 lon=-47.807492
  [REPEATER] RAO-IRAJA-8269 (8269a843c379...)  lat=-21.205180 lon=-47.807730
  [CONTACT] Ricardo PY2RIC 2 (5e0c7e36b176...)  lat=-21.180248 lon=-47.801279
  [ROOM] RAO-ROOMSERVER-D59D (d59dac4a4d36...)  lat=-21.178000 lon=-47.810750
  ...
======================================================================

📺 Getting channels...
  [0] Public (hash=11) role=MEMBER

📢 Sending advert...
   ✅ Sent
📥 Auto message fetching started

📚 Loaded 15 known nodes from known_nodes.json

======================================================================
🎯 MONITORING ALL CHANNELS + ADVERTISEMENTS
💾 Known nodes saved to: known_nodes.json
======================================================================
```

### Monitoramento em Tempo Real

**Mensagem de canal (qualquer canal):**
```
======================================================================
📢 CHANNEL MESSAGE #0
======================================================================
  Text: Fernando PR2YZ: Boa noite. Teste
  Time: 1788474765
  Hops: 0
  SNR:  13.25dB
======================================================================
```

**Mensagem direta (DM):**
```
======================================================================
📩 CONTACT MESSAGE (DM)
======================================================================
  Text: Olá, tudo bem?
  Time: 1788475000
  Hops: 1
  SNR:  10.5dB
======================================================================
```

**Anúncio (Advertisement) - NOVO:**
```
======================================================================
📢 ADVERTISEMENT RECEIVED
======================================================================
  Name:       João Silva
  Public Key: a1b2c3d4e5f6...
  Location:   lat=-21.123456 lon=-47.654321
  Type:       1
  TX Power:   22dBm
  RSSI/SNR:   -55dBm / 12.5dB
  Hops:       2
  Time:       1788477000
======================================================================

💾 Saved/updated João Silva (a1b2c3d4e5f6...) in known_nodes.json
```

**Pacote LoRa bruto (RX_LOG):**
```
📡 RX: type=GRP_TXT route=FLOOD rssi=-58dBm snr=12.0dB len=37 path=
📡 RX: type=TEXT_MSG route=DIRECT rssi=-53dBm snr=11.75dB len=39 path=3189
```

## 📁 Arquivo known_nodes.json

O monitor cria/atualiza automaticamente o arquivo `known_nodes.json` com todos os nós que enviam advertisements:

```json
{
  "a1b2c3d4e5f6...": {
    "name": "João Silva",
    "public_key": "a1b2c3d4e5f6...",
    "lat": -21.123456,
    "lon": -47.654321,
    "type": 1,
    "tx_power": 22,
    "last_seen": 1788477000,
    "last_rssi": -55,
    "last_snr": 12.5,
    "last_hops": 2
  }
}
```

**Campos armazenados:**
| Campo | Descrição |
|-------|-----------|
| `name` | Nome do nó (adv_name) |
| `public_key` | Chave pública completa (hex) |
| `lat` / `lon` | Localização do último advert |
| `type` | Tipo: 1=Contact, 2=Repeater, 3=Room, 4=Sensor |
| `tx_power` | Potência de transmissão (dBm) |
| `last_seen` | Timestamp Unix do último advert |
| `last_rssi` | RSSI do último pacote recebido |
| `last_snr` | SNR do último pacote recebido |
| `last_hops` | Número de saltos (path_len) |

## 🎯 O que Captura

| Evento | Descrição |
|--------|-----------|
| `CHANNEL_MSG_RECV` | Mensagens em **todos os canais/grupos** (não só Public) |
| `CONTACT_MSG_RECV` | Mensagens diretas entre contatos (DMs) |
| `RX_LOG_DATA` | Pacotes LoRa recebidos com metadados RF |
| `LOG_DATA` | Logs de transmissão |
| `ADVERTISEMENT` | **Anúncios de presença** - captura e salva nó |
| `ADVERT_PATH` | Informações de caminho do advert |
| `DEVICE_INFO` | Informações do hardware/firmware |
| `CONTACTS` | Lista completa de contatos |
| `SELF_INFO` | Configuração do próprio nó |
| `BATTERY` | Nível de bateria |
| `TELEMETRY_RESPONSE` | Dados de telemetria |
| `STATS_*` | Estatísticas (core, radio, packets) |
| `PATH_UPDATE` | Atualizações de roteamento |

## 🌤️ Consulta METAR (REDEMET)

O bot responde automaticamente a **mensagens diretas (DMs)** contendo o comando `METAR <ICAO>`.

### Formato do comando
```
METAR SBRP
metar SBGR
Metar   SBGL
```

- Case-insensitive (maiúsculo/minúsculo não importa)
- Espaçamento flexível
- Código ICAO do aeroporto (4 letras, ex: SBRP, SBGR, SBGL, SBPA)

### Resposta do bot
O bot consulta a API da REDEMET (api-redemet.decea.mil.br) e retorna:
- Código METAR completo
- Data/hora do recebimento (HH:MM DD/MM/AAAA)
- Limitado a **130 caracteres** (padrão MeshCore) - se exceder, remove o timestamp

### Exemplos
**Entrada (DM):**
```
METAR SBRP
```

**Saída (DM de resposta):**
```
METAR SBRP 042000Z 25007KT CAVOK 34/09 Q1011= 20:00 04/09/2026
```

**Se não encontrar:**
```
METAR nao encontrado para SBRP
```

**Formato inválido:**
```
Formato: METAR <AEROPORTO> (ex: METAR SBRP)
```

> **Nota:** O bot **não responde em canais públicos** para não poluir a rede - apenas em DMs (mensagens privadas).

## 🌤️ Tempo/Clima no Canal #Public (Ctrl+F e Automático)

Ao pressionar **Ctrl+F**, ou automaticamente via cron (se habilitado), o monitor consulta a API **Open-Meteo** para Ribeirão Preto e publica uma mensagem formatada no canal **#Public** (índice 0, configurável).

### Formato da mensagem (um item por linha, máx. 130 chars)

```
Clima RAO ☀️ Céu limpo
25°C 65%
🌕 Lua cheia
14:30 05/09/2026
```

### Componentes

| Item | Descrição | Fonte |
|------|-----------|-------|
| `Clima RAO ☀️ Céu limpo` | Prefixo + emoji do tempo + **descrição em PT** | `weather_code` |
| `25°C 65%` | Temperatura + umidade relativa | `temperature_2m`, `relative_humidity_2m` |
| `🌕 Lua cheia` | Emoji da fase da lua + **descrição em PT** | `moon_phase` (daily) |
| `14:30 05/09/2026` | Hora e data local | `datetime.now()` (timezone America/Sao_Paulo) |

### Emojis de tempo (weather_code)

| Código | Condição | Emoji | Descrição PT |
|--------|----------|-------|--------------|
| 0 | Céu limpo | ☀️ | Céu limpo |
| 1 | Principalmente limpo | 🌤️ | Principalmente limpo |
| 2 | Parcialmente nublado | ⛅ | Parcialmente nublado |
| 3 | Nublado | ☁️ | Nublado |
| 45, 48 | Neblina | 🌫️ | Neblina / Neblina com geada |
| 51-57 | Chuvisco | 🌦️ 🌧️ | Chuvisco leve a denso / congelante |
| 61-67 | Chuva | 🌦️ 🌧️ | Chuva leve a forte / congelante |
| 71-77 | Neve | 🌨️ | Neve leve a forte / grãos |
| 80-82 | Pancadas de chuva | 🌦️ 🌧️ | Pancadas leves a violentas |
| 85-86 | Pancadas de neve | 🌨️ | Pancadas leves a fortes |
| 95-99 | Tempestade | ⛈️ | Trovoada / com granizo |

### Emojis de fase da lua (moon_phase 0.0-1.0)

| Fase | Intervalo | Emoji | Descrição PT |
|------|-----------|-------|--------------|
| Lua Nova | 0.00-0.06 | 🌑 | Lua nova |
| Lua Crescente | 0.06-0.19 | 🌒 | Lua crescente |
| Quarto Crescente | 0.19-0.31 | 🌓 | Quarto crescente |
| Lua Gibosa Crescente | 0.31-0.44 | 🌔 | Lua gibosa crescente |
| Lua Cheia | 0.44-0.56 | 🌕 | Lua cheia |
| Lua Gibosa Minguante | 0.56-0.69 | 🌖 | Lua gibosa minguante |
| Quarto Minguante | 0.69-0.81 | 🌗 | Quarto minguante |
| Lua Minguante | 0.81-0.94 | 🌘 | Lua minguante |
| Lua Nova (fim) | 0.94-1.00 | 🌑 | Lua nova |

### Exemplo de chamada API

```
https://api.open-meteo.com/v1/forecast?latitude=-21.1775&longitude=-47.8103&daily=moon_phase&current=is_day,temperature_2m,relative_humidity_2m,weather_code&timezone=America%2FSao_Paulo&forecast_days=1
```

## ⌨️ Atalhos de Teclado

| Tecla | Ação |
|-------|------|
| **Ctrl+A** | Enviar advert (anúncio de presença) |
| **Ctrl+F** | Enviar tempo/clima para canal #Public |
| **Ctrl+C** | Sair do monitor |

> **Nota:** Ctrl+A e Ctrl+F só funcionam em terminal interativo (TTY). Em execuções não-interativas (pipes, scripts), use Ctrl+C para sair.

## ⚙️ Configuração

As configurações são feitas via arquivo `.env` (copie `.env.example` para `.env` e ajuste):

```bash
# Configuração serial
SERIAL_PORT=/dev/ttyUSB0
BAUDRATE=115200
KNOWN_NODES_FILE=known_nodes.json
BOX_WIDTH=72

# METAR API (REDEMET)
METAR_API_KEY=sua_chave_api
METAR_API_BASE=https://api-redemet.decea.mil.br/mensagens/metar

# Open-Meteo Weather API (Ribeirão Preto)
OPEN_METEO_LATITUDE=-21.1775
OPEN_METEO_LONGITUDE=-47.8103
OPEN_METEO_BASE=https://api.open-meteo.com/v1/forecast

MAX_MESSAGE_LENGTH=130

# Auto Weather Sending (Cron via variável de ambiente)
WEATHER_AUTO_SEND_ENABLED=false
WEATHER_AUTO_SEND_INTERVAL=30
WEATHER_AUTO_SEND_CHANNEL=0
```

### Variáveis de ambiente principais

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `SERIAL_PORT` | Porta serial do nó MeshCore | `/dev/ttyUSB0` |
| `BAUDRATE` | Baud rate da conexão | `115200` |
| `OPEN_METEO_LATITUDE` | Latitude para consulta de tempo | `-21.1775` (Ribeirão Preto) |
| `OPEN_METEO_LONGITUDE` | Longitude para consulta de tempo | `-47.8103` (Ribeirão Preto) |
| `MAX_MESSAGE_LENGTH` | Tamanho máximo da mensagem MeshCore | `130` |
| `WEATHER_AUTO_SEND_ENABLED` | Habilita envio automático de tempo (true/false) | `false` |
| `WEATHER_AUTO_SEND_INTERVAL` | Intervalo em minutos para envio automático | `30` |
| `WEATHER_AUTO_SEND_CHANNEL` | Índice do canal destino (0 = #Public) | `0` |

## 🐛 Solução de Problemas

### "Failed to connect"
- Verifique se a porta está correta: `ls /dev/ttyUSB*`
- Verifique permissões: `ls -la /dev/ttyUSB2` (deve ser `crw-rw---- root dialout`)
- Adicione usuário ao grupo: `sudo usermod -a -G dialout $USER` + logout/login
- Nó pode estar em sleep - tente reiniciar o hardware

### "No response from meshcore node"
- Verifique se é um **Companion** (não Repeater)
- Cabo USB de dados (não apenas carregamento)
- Tente baud rates diferentes se necessário

### Mensagens não aparecem
- Certifique-se que há tráfego na rede MeshCore
- O nó deve estar online e conectado à rede
- Verifique se `auto_message_fetching` iniciou (log "Auto message fetching started")

### known_nodes.json não é criado
- O arquivo só é criado quando o **primeiro advertisement** é recebido
- Nós só enviam advertisements periodicamente (configurável no nó)
- Verifique se há outros nós ativos na rede

## 📚 Referências

- [MeshCore Python SDK](https://github.com/meshcore-dev/meshcore_py)
- [MeshCore Protocol](https://meshcore.co.uk)
- [meshcore-cli](https://github.com/fdlamotte/meshcore-cli)

## 📄 Licença

MIT License - Use livremente para projetos pessoais ou comerciais.