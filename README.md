# MeshCore Monitor

Aplicação Python para monitorar um nó MeshCore Companion via porta serial, exibindo todos os dados recebidos em tempo real no console.

## 📋 Funcionalidades

- **Conexão serial** com nó MeshCore Companion (porta `/dev/ttyUSB2` @ 115200 baud)
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

## 🔧 Requisitos

- Python 3.10+
- Biblioteca `meshcore` (SDK oficial Python)
- Permissão de acesso à porta serial (`dialout` group)

## 📦 Instalação

```bash
# Instalar SDK MeshCore
pip install meshcore

# Verificar porta serial
ls -la /dev/ttyUSB*
# Deve mostrar /dev/ttyUSB2 (ajuste no código se diferente)

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
#   Ctrl+C = Sair
```

**Nota:** O atalho Ctrl+A funciona apenas quando executado em terminal interativo (TTY).

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

## ⌨️ Atalhos de Teclado

| Tecla | Ação |
|-------|------|
| **Ctrl+A** | Enviar advert (anúncio de presença) |
| **Ctrl+C** | Sair do monitor |

> **Nota:** Ctrl+A só funciona em terminal interativo (TTY). Em execuções não-interativas (pipes, scripts), use Ctrl+C para sair.

## ⚙️ Configuração

Edite `meshcore_monitor.py` para ajustar:

```python
SERIAL_PORT = "/dev/ttyUSB2"  # Porta serial do nó
BAUDRATE = 115200              # Baud rate (padrão MeshCore)
KNOWN_NODES_FILE = Path("known_nodes.json")  # Arquivo de nós conhecidos
```

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