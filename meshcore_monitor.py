#!/usr/bin/env python3
"""
MeshCore Monitor - Connects to a MeshCore companion node via serial
and displays all received data formatted correctly.
- Monitors all public channels (#)
- Captures advertisements and saves known nodes to file
- Ctrl+A: Send advert
- Ctrl+F: Send weather/time to #Public channel
"""
import asyncio
import json
import os
import re
import sys
import termios
import time
import tty
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from meshcore import MeshCore, EventType
from meshcore.commands import MessagingCommands

from dotenv import load_dotenv

load_dotenv()

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
BAUDRATE = int(os.getenv("BAUDRATE", "115200"))
KNOWN_NODES_FILE = Path(os.getenv("KNOWN_NODES_FILE", "known_nodes.json"))

# Display width for boxes
BOX_WIDTH = int(os.getenv("BOX_WIDTH", "72"))

# METAR API Configuration
METAR_API_KEY = os.getenv("METAR_API_KEY", "")
METAR_API_BASE = os.getenv("METAR_API_BASE", "https://api-redemet.decea.mil.br/mensagens/metar")

# Open-Meteo Weather API Configuration
OPEN_METEO_LATITUDE = float(os.getenv("OPEN_METEO_LATITUDE", "-21.1775"))
OPEN_METEO_LONGITUDE = float(os.getenv("OPEN_METEO_LONGITUDE", "-47.8103"))
OPEN_METEO_BASE = os.getenv("OPEN_METEO_BASE", "https://api.open-meteo.com/v1/forecast")

MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "130"))

# Auto Weather Sending Configuration
WEATHER_AUTO_SEND_ENABLED = os.getenv("WEATHER_AUTO_SEND_ENABLED", "false").lower() == "true"
WEATHER_AUTO_SEND_INTERVAL = int(os.getenv("WEATHER_AUTO_SEND_INTERVAL", "30"))
WEATHER_AUTO_SEND_CHANNEL = int(os.getenv("WEATHER_AUTO_SEND_CHANNEL", "0"))

# Bot Node Name Configuration (for @mentions in channels)
MY_NODE_NAME = os.getenv("MY_NODE_NAME", "MeshMonitor")


def wrap_text(text, width=BOX_WIDTH - 4):
    """Wrap text to fit in box."""
    if not text:
        return [""]
    lines = text.split('\n')
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=width) or [""])
    return wrapped


async def fetch_metar(airport: str) -> Optional[str]:
    """Fetch METAR data from REDEMET API for given airport."""
    today = datetime.now().strftime("%Y%m%d")
    url = f"{METAR_API_BASE}/{airport}?api_key={METAR_API_KEY}&inicialData={today}&finalData={today}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                
                if not data.get("status") or not data.get("data", {}).get("data"):
                    return None
                
                metar_data = data["data"]["data"][0]
                mens = metar_data.get("mens", "")
                recebimento = metar_data.get("recebimento", "")
                
                if not mens:
                    return None
                
                # Parse timestamp from recebimento (format: "2026-09-04 20:00:00")
                timestamp_str = ""
                if recebimento:
                    try:
                        dt = datetime.strptime(recebimento, "%Y-%m-%d %H:%M:%S")
                        timestamp_str = dt.strftime("%H:%M %d/%m/%Y")
                    except ValueError:
                        pass
                
                # Format message: "METAR ... HH:MM DD/MM/YYYY"
                if timestamp_str:
                    formatted = f"{mens} {timestamp_str}"
                else:
                    formatted = mens
                
                # Ensure max 130 chars - if too long, remove timestamp
                if len(formatted) > MAX_MESSAGE_LENGTH:
                    formatted = mens
                    if len(formatted) > MAX_MESSAGE_LENGTH:
                        formatted = formatted[:MAX_MESSAGE_LENGTH]
                
                return formatted
    except Exception as e:
        print(f"⚠️  Error fetching METAR: {e}")
        return None


WEATHER_CODE_EMOJI = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌧️",
    55: "🌧️",
    56: "🌧️",
    57: "🌧️",
    61: "🌦️",
    63: "🌧️",
    65: "🌧️",
    66: "🌧️",
    67: "🌧️",
    71: "🌨️",
    73: "🌨️",
    75: "🌨️",
    77: "🌨️",
    80: "🌦️",
    81: "🌧️",
    82: "🌧️",
    85: "🌨️",
    86: "🌨️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}

WEATHER_CODE_DESCRIPTION_PT = {
    0: "Céu limpo",
    1: "Principalmente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    48: "Neblina com depósito de geada",
    51: "Chuvisco leve",
    53: "Chuvisco moderado",
    55: "Chuvisco denso",
    56: "Chuvisco congelante leve",
    57: "Chuvisco congelante denso",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante leve",
    67: "Chuva congelante forte",
    71: "Neve leve",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas de chuva leves",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva violentas",
    85: "Pancadas de neve leves",
    86: "Pancadas de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo leve",
    99: "Trovoada com granizo forte",
}

MOON_PHASE_EMOJI = {
    (0.000, 0.0625): "🌑",
    (0.0625, 0.1875): "🌒",
    (0.1875, 0.3125): "🌓",
    (0.3125, 0.4375): "🌔",
    (0.4375, 0.5625): "🌕",
    (0.5625, 0.6875): "🌖",
    (0.6875, 0.8125): "🌗",
    (0.8125, 0.9375): "🌘",
    (0.9375, 1.000): "🌑",
}

MOON_PHASE_DESCRIPTION_PT = {
    (0.000, 0.0625): "Lua nova",
    (0.0625, 0.1875): "Lua crescente",
    (0.1875, 0.3125): "Quarto crescente",
    (0.3125, 0.4375): "Lua gibosa crescente",
    (0.4375, 0.5625): "Lua cheia",
    (0.5625, 0.6875): "Lua gibosa minguante",
    (0.6875, 0.8125): "Quarto minguante",
    (0.8125, 0.9375): "Lua minguante",
    (0.9375, 1.000): "Lua nova",
}


def get_moon_phase_emoji(phase: float) -> str:
    for (start, end), emoji in MOON_PHASE_EMOJI.items():
        if start <= phase < end:
            return emoji
    return "🌑"


def get_moon_phase_description_pt(phase: float) -> str:
    for (start, end), desc in MOON_PHASE_DESCRIPTION_PT.items():
        if start <= phase < end:
            return desc
    return "Lua nova"


async def fetch_weather() -> Optional[dict]:
    """Fetch weather data from Open-Meteo API for Ribeirao Preto."""
    url = (
        f"{OPEN_METEO_BASE}?"
        f"latitude={OPEN_METEO_LATITUDE}&longitude={OPEN_METEO_LONGITUDE}"
        f"&daily=moon_phase"
        f"&current=is_day,temperature_2m,relative_humidity_2m,weather_code"
        f"&timezone=America%2FSao_Paulo&forecast_days=1"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    print(f"⚠️  Weather API error: HTTP {response.status}")
                    return None
                data = await response.json()
                return data
    except Exception as e:
        print(f"⚠️  Error fetching weather: {e}")
        return None


def format_weather_message(weather_data: dict) -> Optional[str]:
    """Format weather data into a message with one item per line, max 130 chars."""
    if not weather_data:
        return None

    current = weather_data.get("current", {})
    daily = weather_data.get("daily", {})

    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    weather_code = current.get("weather_code")
    is_day = current.get("is_day", 1)

    moon_phase = daily.get("moon_phase", [0])[0] if daily.get("moon_phase") else 0

    now = datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%d/%m/%Y")

    weather_emoji = WEATHER_CODE_EMOJI.get(weather_code, "❓")
    weather_desc = WEATHER_CODE_DESCRIPTION_PT.get(weather_code, "Desconhecido")
    moon_emoji = get_moon_phase_emoji(moon_phase)
    moon_desc = get_moon_phase_description_pt(moon_phase)

    lines = [
        f"Clima RAO {weather_emoji} {weather_desc}",
        f"{temp}°C {humidity}%",
        f"{moon_emoji} {moon_desc}",
        f"{time_str} {date_str}",
    ]

    message = "\n".join(lines)

    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[:MAX_MESSAGE_LENGTH]

    return message


def parse_metar_command(text: str) -> Optional[str]:
    """Parse METAR command from text. Returns airport code or None."""
    # Match METAR <AIRPORT> case insensitive, flexible spacing
    match = re.search(r'\bMETAR\s+([A-Z0-9]{4})\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


async def handle_metar_request(meshcore, event, text: str, is_channel: bool, channel_idx: Optional[int] = None, sender_pubkey: Optional[str] = None):
    """Handle METAR request and send response."""
    airport = parse_metar_command(text)
    if not airport:
        error_msg = "Formato: METAR <AEROPORTO> (ex: METAR SBRP)"
        if is_channel and channel_idx is not None:
            await meshcore.commands.send_chan_msg(channel_idx, error_msg)
        elif not is_channel and sender_pubkey:
            await meshcore.commands.send_msg(sender_pubkey, error_msg)
        return
    
    metar_result = await fetch_metar(airport)
    if not metar_result:
        error_msg = f"METAR nao encontrado para {airport}"
        if is_channel and channel_idx is not None:
            await meshcore.commands.send_chan_msg(channel_idx, error_msg)
        elif not is_channel and sender_pubkey:
            await meshcore.commands.send_msg(sender_pubkey, error_msg)
        return
    
    if is_channel and channel_idx is not None:
        await meshcore.commands.send_chan_msg(channel_idx, metar_result)
    elif not is_channel and sender_pubkey:
        # Set flood scope to "*" (force unscoped) so the response floods through the mesh network
        await meshcore.commands.set_flood_scope("*", force_unscoped=True)
        await meshcore.commands.send_msg(sender_pubkey, metar_result)


def load_known_nodes():
    """Load known nodes from file."""
    if KNOWN_NODES_FILE.exists():
        try:
            with open(KNOWN_NODES_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Error loading known nodes: {e}")
    return {}


def save_known_nodes(nodes):
    """Save known nodes to file."""
    try:
        with open(KNOWN_NODES_FILE, 'w') as f:
            json.dump(nodes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️  Error saving known nodes: {e}")


def format_contact(contact):
    """Format contact info for display."""
    if not isinstance(contact, dict):
        return f"  {contact}"
    name = contact.get('adv_name', contact.get('name', 'unnamed'))
    pubkey = contact.get('public_key', '')[:12]
    ctype = contact.get('type', 0)
    type_names = {0: 'CLI', 1: 'CONTACT', 2: 'REPEATER', 3: 'ROOM', 4: 'SENSOR'}
    lat = contact.get('adv_lat', 0)
    lon = contact.get('adv_lon', 0)
    last_adv = contact.get('last_advert', 0)
    return f"  [{type_names.get(ctype, '?')}] {name} ({pubkey}...)  lat={lat:.6f} lon={lon:.6f}  last={last_adv}"


def format_channel(channel):
    """Format channel info for display."""
    if not isinstance(channel, dict):
        return f"  {channel}"
    idx = channel.get('idx', channel.get('index', '?'))
    name = channel.get('channel_name', channel.get('name', 'unnamed'))
    chash = channel.get('channel_hash', channel.get('hash', ''))[:8]
    role = channel.get('role', 0)
    role_names = {0: 'MEMBER', 1: 'ADMIN', 2: 'OWNER'}
    return f"  [{idx}] {name} (hash={chash}) role={role_names.get(role, role)}"


def _print_lines(lines):
    """Print lines with explicit flush to avoid terminal rendering issues."""
    out = '\r\n'.join(lines) + '\r\n'
    sys.stdout.write(out)
    sys.stdout.flush()


async def on_contact_message(event, meshcore=None):
    """Handle incoming contact messages (DMs)."""
    msg = event.payload or {}
    text = msg.get('text', '')
    sender_pubkey = msg.get('from', msg.get('sender_pubkey', msg.get('sender', '')))
    
    # If no direct pubkey field, try pubkey_prefix and lookup in known_nodes
    if not sender_pubkey:
        pubkey_prefix = msg.get('pubkey_prefix', '')
        if pubkey_prefix:
            # Look up full pubkey in known_nodes
            known_nodes = load_known_nodes()
            for full_pubkey, node_info in known_nodes.items():
                if full_pubkey.startswith(pubkey_prefix):
                    sender_pubkey = full_pubkey
                    break
    
    lines = [
        f"\n{'='*BOX_WIDTH}",
        f"📩 CONTACT MESSAGE (DM)",
        f"{'='*BOX_WIDTH}",
    ]
    lines.extend(f"  {line}" for line in wrap_text(text))
    lines.extend([
        f"  Time: {msg.get('sender_timestamp', msg.get('timestamp', 'unknown'))}",
        f"  Hops: {msg.get('path_len', '?')}",
        f"  SNR:  {msg.get('SNR', msg.get('rssi', '?'))}dB",
        f"{'='*BOX_WIDTH}\n",
    ])
    _print_lines(lines)
    
    # Handle METAR command in DMs
    if meshcore:
        await handle_metar_request(meshcore, event, text, is_channel=False, sender_pubkey=sender_pubkey)


async def on_channel_message(event, meshcore=None):
    """Handle incoming channel messages (all channels)."""
    msg = event.payload or {}
    channel_idx = msg.get('channel_idx', '?')
    text = msg.get('text', '')
    lines = [
        f"\n{'='*BOX_WIDTH}",
        f"📢 CHANNEL MESSAGE #{channel_idx}",
        f"{'='*BOX_WIDTH}",
    ]
    lines.extend(f"  {line}" for line in wrap_text(text))
    lines.extend([
        f"  Time: {msg.get('sender_timestamp', msg.get('timestamp', 'unknown'))}",
        f"  Hops: {msg.get('path_len', '?')}",
        f"  SNR:  {msg.get('SNR', msg.get('rssi', '?'))}dB",
        f"{'='*BOX_WIDTH}\n",
    ])
    _print_lines(lines)

    # Handle @mentions for METAR and CLIMA commands in channel messages
    if meshcore and channel_idx is not None:
        await handle_channel_mention(meshcore, channel_idx, text)


async def handle_channel_mention(meshcore, channel_idx: int, text: str):
    """Handle @mentions in channel messages for METAR and CLIMA commands."""
    if not text:
        return
    
    # Use the full node name with robot emoji for mention matching
    bot_name_with_emoji = f"{MY_NODE_NAME} 🤖"
    
    # Check for mention pattern: @[node_name] COMMAND
    mention_pattern = rf'@\[{re.escape(bot_name_with_emoji)}\]\s+(.+)'
    match = re.search(mention_pattern, text, re.IGNORECASE)
    if not match:
        return
    
    command_text = match.group(1).strip()
    command_upper = command_text.upper()
    
    # Handle HELP/AJUDA command
    if re.search(r'\b(AJUDA|HELP)\b', command_upper):
        print(f"❓ Channel #{channel_idx}: @mention AJUDA/HELP request")
        help_msg = (
            f"Comandos disponiveis para @[{bot_name_with_emoji}]:\n"
            f"  METAR <ICAO> - Consulta METAR (ex: METAR SBRP)\n"
            f"  CLIMA - Previsao do tempo atual\n"
            f"  AJUDA / HELP - Esta mensagem"
        )
        await meshcore.commands.send_chan_msg(channel_idx, help_msg)
        print(f"   ✅ Help sent to channel #{channel_idx}")
        return
    
    # Handle METAR command
    metar_match = re.search(r'\bMETAR\s+([A-Z0-9]{4})\b', command_text, re.IGNORECASE)
    if metar_match:
        airport = metar_match.group(1).upper()
        print(f"📍 Channel #{channel_idx}: @mention METAR request for {airport}")
        metar_result = await fetch_metar(airport)
        if metar_result:
            await meshcore.commands.send_chan_msg(channel_idx, metar_result)
            print(f"   ✅ METAR sent to channel #{channel_idx}")
        else:
            error_msg = f"METAR nao encontrado para {airport}"
            await meshcore.commands.send_chan_msg(channel_idx, error_msg)
            print(f"   ❌ {error_msg}")
        return
    
    # Handle METAR without airport code
    if re.search(r'\bMETAR\b', command_upper):
        print(f"⚠️  Channel #{channel_idx}: @mention METAR without airport code")
        help_msg = "Para METAR adicione o codigo ICAO: METAR <AEROPORTO> (ex: METAR SBRP)"
        await meshcore.commands.send_chan_msg(channel_idx, help_msg)
        print(f"   ✅ METAR help sent to channel #{channel_idx}")
        return
    
    # Handle CLIMA command
    if re.search(r'\bCLIMA\b', command_upper):
        print(f"🌤️  Channel #{channel_idx}: @mention CLIMA request")
        weather_data = await fetch_weather()
        if weather_data:
            message = format_weather_message(weather_data)
            if message:
                await meshcore.commands.send_chan_msg(channel_idx, message)
                print(f"   ✅ Weather sent to channel #{channel_idx}")
            else:
                await meshcore.commands.send_chan_msg(channel_idx, "Erro ao formatar mensagem de clima")
        else:
            await meshcore.commands.send_chan_msg(channel_idx, "Erro ao buscar dados de clima")
        return
    
    # Unrecognized command
    print(f"❓ Channel #{channel_idx}: @mention unrecognized command: {command_text}")
    help_msg = (
        f"Comando nao reconhecido: {command_text}\n"
        f"Use @[{MY_NODE_NAME}] AJUDA para ver comandos disponiveis"
    )
    await meshcore.commands.send_chan_msg(channel_idx, help_msg)
    print(f"   ✅ Unrecognized command help sent to channel #{channel_idx}")


async def on_rx_log(event):
    """Handle RX log events (raw LoRa packet info)."""
    rx = event.payload or {}
    ptype = rx.get('payload_typename', '?')
    rtype = rx.get('route_typename', '?')
    rssi = rx.get('rssi', '?')
    snr = rx.get('snr', '?')
    plen = rx.get('payload_length', '?')
    path = rx.get('path', '')
    # Compact single-line format
    sys.stdout.write(f"\r\n📡 RX: {ptype}/{rtype} rssi={rssi}dBm snr={snr}dB len={plen} path={path}\r\n")
    sys.stdout.flush()


async def on_log_data(event):
    """Handle LOG_DATA events."""
    log = event.payload or {}
    sys.stdout.write(f"\r\n📝 LOG: {log}\r\n")
    sys.stdout.flush()


async def on_node_info(event):
    """Handle node info events."""
    info = event.payload or {}
    lines = [
        f"\n{'='*BOX_WIDTH}",
        f"📋 NODE INFO",
        f"{'='*BOX_WIDTH}",
    ]
    lines.extend(f"  {k}: {v}" for k, v in info.items())
    lines.append(f"{'='*BOX_WIDTH}\n")
    _print_lines(lines)


async def on_contact_list(event):
    """Handle contact list events."""
    payload = event.payload
    lines = [
        f"\n{'='*BOX_WIDTH}",
        f"👥 CONTACT LIST",
        f"{'='*BOX_WIDTH}",
    ]
    if isinstance(payload, dict):
        for key, contact in payload.items():
            if isinstance(contact, dict):
                lines.append(format_contact(contact))
            else:
                lines.append(f"  {key}: {contact}")
    elif isinstance(payload, list):
        for contact in payload:
            if isinstance(contact, dict):
                lines.append(format_contact(contact))
    else:
        lines.append(f"  {payload}")
    lines.append(f"{'='*BOX_WIDTH}\n")
    _print_lines(lines)


async def on_self_info(event):
    """Handle self info events."""
    info = event.payload or {}
    lines = [
        f"\n{'='*BOX_WIDTH}",
        f"🔧 SELF INFO",
        f"{'='*BOX_WIDTH}",
    ]
    lines.extend(f"  {k}: {v}" for k, v in info.items())
    lines.append(f"{'='*BOX_WIDTH}\n")
    _print_lines(lines)


async def on_advertisement(event, known_nodes):
    """Handle advertisement events - capture advertiser info."""
    adv = event.payload or {}
    
    # Extract advertiser info
    pubkey = adv.get('public_key', adv.get('from', ''))
    name = adv.get('adv_name', adv.get('name', 'unknown'))
    lat = adv.get('adv_lat', adv.get('lat', 0))
    lon = adv.get('adv_lon', adv.get('lon', 0))
    adv_type = adv.get('adv_type', adv.get('type', 0))
    tx_power = adv.get('tx_power', '?')
    snr = adv.get('SNR', adv.get('snr', '?'))
    rssi = adv.get('rssi', '?')
    path_len = adv.get('path_len', '?')
    timestamp = adv.get('timestamp', int(time.time()))
    
    lines = [
        f"\n{'='*BOX_WIDTH}",
        f"📢 ADVERTISEMENT RECEIVED",
        f"{'='*BOX_WIDTH}",
        f"  Name:       {name}",
        f"  Public Key: {pubkey}",
        f"  Location:   lat={lat:.6f} lon={lon:.6f}" if lat != 0 or lon != 0 else "  Location:   not set",
        f"  Type:       {adv_type}",
        f"  TX Power:   {tx_power}dBm",
        f"  RSSI/SNR:   {rssi}dBm / {snr}dB",
        f"  Hops:       {path_len}",
        f"  Time:       {timestamp}",
        f"{'='*BOX_WIDTH}\n",
    ]
    _print_lines(lines)
    
    # Save to known nodes
    if pubkey:
        known_nodes[pubkey] = {
            'name': name,
            'public_key': pubkey,
            'lat': lat,
            'lon': lon,
            'type': adv_type,
            'tx_power': tx_power,
            'last_seen': timestamp,
            'last_rssi': rssi,
            'last_snr': snr,
            'last_hops': path_len,
        }
        save_known_nodes(known_nodes)
        sys.stdout.write(f"\r\n💾 Saved/updated {name} ({pubkey[:12]}...) in known_nodes.json\r\n")
        sys.stdout.flush()


async def on_advert_path(event, known_nodes):
    """Handle advertisement path events."""
    adv = event.payload or {}
    sys.stdout.write(f"\r\n📍 ADVERT PATH: {adv}\r\n")
    sys.stdout.flush()


async def on_generic_event(event):
    """Catch-all for other events."""
    ename = event.type.name
    if ename in ('NO_MORE_MSGS', 'OK', 'CONNECTED', 'DISCONNECTED', 'ACK', 'MESSAGES_WAITING'):
        return  # Skip noisy events
    sys.stdout.write(f"\r\n🔔 {ename}: {event.payload}\r\n")
    sys.stdout.flush()


async def connect_with_retry(max_retries=3):
    """Connect to MeshCore with retry logic."""
    for attempt in range(max_retries):
        print(f"🔌 Connecting to MeshCore on {SERIAL_PORT} @ {BAUDRATE} (attempt {attempt+1}/{max_retries})...")
        try:
            meshcore = await MeshCore.create_serial(SERIAL_PORT, BAUDRATE, debug=False)
            if meshcore is not None:
                print("✅ Connected!")
                return meshcore
        except Exception as e:
            print(f"   Attempt {attempt+1} failed: {e}")
        
        if attempt < max_retries - 1:
            print(f"   Waiting 3s before retry...")
            await asyncio.sleep(3)
    
    return None


async def send_advert_shortcut(meshcore):
    """Send advert on Ctrl+A."""
    print("\n📢 Sending advert (Ctrl+A)...")
    result = await meshcore.commands.send_advert()
    if result.type != EventType.ERROR:
        print("   ✅ Sent")
    else:
        print(f"   ❌ {result.payload}")


async def send_weather_shortcut(meshcore):
    """Send weather/time to #Public channel on Ctrl+F."""
    print("\n🌤️  Fetching weather (Ctrl+F)...")
    weather_data = await fetch_weather()
    if not weather_data:
        print("   ❌ Failed to fetch weather")
        return
    
    message = format_weather_message(weather_data)
    if not message:
        print("   ❌ Failed to format weather message")
        return
    
    print(f"   Sending to #Public (channel 0):")
    for line in message.split('\n'):
        print(f"     {line}")
    
    result = await meshcore.commands.send_chan_msg(0, message)
    if result.type != EventType.ERROR:
        print("   ✅ Sent to #Public")
    else:
        print(f"   ❌ {result.payload}")


async def send_weather_to_channel(meshcore, channel_idx: int):
    """Send weather to specified channel."""
    weather_data = await fetch_weather()
    if not weather_data:
        print("   ❌ Failed to fetch weather for auto-send")
        return
    
    message = format_weather_message(weather_data)
    if not message:
        print("   ❌ Failed to format weather message for auto-send")
        return
    
    result = await meshcore.commands.send_chan_msg(channel_idx, message)
    if result.type != EventType.ERROR:
        print(f"   ✅ Auto weather sent to channel {channel_idx}")
    else:
        print(f"   ❌ Auto weather send failed: {result.payload}")


async def auto_weather_sender(meshcore):
    """Background task to periodically send weather to channel."""
    if not WEATHER_AUTO_SEND_ENABLED:
        return
    
    interval_seconds = WEATHER_AUTO_SEND_INTERVAL * 60
    channel_idx = WEATHER_AUTO_SEND_CHANNEL
    
    print(f"🌤️  Auto weather sending enabled: every {WEATHER_AUTO_SEND_INTERVAL} min to channel #{channel_idx}")
    
    # Send immediately on start
    await send_weather_to_channel(meshcore, channel_idx)
    
    while True:
        await asyncio.sleep(interval_seconds)
        await send_weather_to_channel(meshcore, channel_idx)


async def keyboard_listener(meshcore):
    """Listen for keyboard input (Ctrl+A, Ctrl+F)."""
    fd = sys.stdin.fileno()
    if not sys.stdin.isatty():
        # Not a TTY (e.g., piped input), just wait
        await asyncio.Event().wait()
        return
    
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.read, 1)
            if ch == '\x01':  # Ctrl+A
                await send_advert_shortcut(meshcore)
            elif ch == '\x06':  # Ctrl+F
                await send_weather_shortcut(meshcore)
            elif ch == '\x03':  # Ctrl+C
                raise KeyboardInterrupt
            await asyncio.sleep(0.05)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def main():
    # Load known nodes
    known_nodes = load_known_nodes()
    if known_nodes:
        print(f"📚 Loaded {len(known_nodes)} known nodes from {KNOWN_NODES_FILE}")
    
    meshcore = await connect_with_retry()
    if meshcore is None:
        print("❌ Failed to connect after retries")
        sys.exit(1)

    # Advertisement handlers with known_nodes reference
    async def advert_handler(e):
        await on_advertisement(e, known_nodes)
    
    async def advert_path_handler(e):
        await on_advert_path(e, known_nodes)
    
    async def channel_msg_handler(e):
        await on_channel_message(e, meshcore)
    
    async def contact_msg_handler(e):
        await on_contact_message(e, meshcore)
    
    # Subscribe to events
    subscriptions = [
        meshcore.subscribe(EventType.CONTACT_MSG_RECV, contact_msg_handler),
        meshcore.subscribe(EventType.CHANNEL_MSG_RECV, channel_msg_handler),
        meshcore.subscribe(EventType.RX_LOG_DATA, on_rx_log),
        meshcore.subscribe(EventType.LOG_DATA, on_log_data),
        meshcore.subscribe(EventType.DEVICE_INFO, on_node_info),
        meshcore.subscribe(EventType.CONTACTS, on_contact_list),
        meshcore.subscribe(EventType.SELF_INFO, on_self_info),
        
        # Advertisement handlers with known_nodes reference
        meshcore.subscribe(EventType.ADVERTISEMENT, advert_handler),
        meshcore.subscribe(EventType.ADVERT_PATH, advert_path_handler),
        
        meshcore.subscribe(EventType.CONTACT_DELETED, on_generic_event),
        meshcore.subscribe(EventType.CONTACTS_FULL, on_generic_event),
        meshcore.subscribe(EventType.MSG_SENT, on_generic_event),
        meshcore.subscribe(EventType.ACK, on_generic_event),
        meshcore.subscribe(EventType.ERROR, on_generic_event),
        meshcore.subscribe(EventType.PATH_UPDATE, on_generic_event),
        meshcore.subscribe(EventType.TELEMETRY_RESPONSE, on_generic_event),
        meshcore.subscribe(EventType.BATTERY, on_generic_event),
        meshcore.subscribe(EventType.STATS_CORE, on_generic_event),
        meshcore.subscribe(EventType.STATS_RADIO, on_generic_event),
        meshcore.subscribe(EventType.STATS_PACKETS, on_generic_event),
    ]

    # Quick initial queries
    print("\n📋 Getting device info...")
    result = await meshcore.commands.send_device_query()
    if result.type != EventType.ERROR:
        info = result.payload
        print(f"   {info.get('model', '?')} | {info.get('ver', '?')}")
        
        # Validate and set node name if needed
        current_name = info.get('name', info.get('node_name', info.get('adv_name', '')))
        # Append robot emoji to the configured name
        desired_name = f"{MY_NODE_NAME} 🤖"
        if current_name:
            print(f"   Current node name: {current_name}")
            if current_name != desired_name:
                print(f"   ⚠️  Node name differs from desired ({desired_name}), updating...")
                set_name_result = await meshcore.commands.set_name(desired_name)
                if set_name_result.type != EventType.ERROR:
                    print(f"   ✅ Node name updated to: {desired_name}")
                else:
                    print(f"   ❌ Failed to update node name: {set_name_result.payload}")
            else:
                print(f"   ✅ Node name matches desired: {desired_name}")
        else:
            print(f"   ⚠️  Could not determine current node name, setting to: {desired_name}")
            set_name_result = await meshcore.commands.set_name(desired_name)
            if set_name_result.type != EventType.ERROR:
                print(f"   ✅ Node name set to: {desired_name}")
            else:
                print(f"   ❌ Failed to set node name: {set_name_result.payload}")

    # Get contacts
    print("👥 Getting contacts...")
    await meshcore.commands.get_contacts()

    # Get channels
    print("📺 Getting channels...")
    for idx in range(10):
        result = await meshcore.commands.get_channel(idx)
        if result.type != EventType.ERROR and result.payload:
            ch = result.payload
            name = ch.get('channel_name', '').strip()
            if name:  # Only show named channels
                ch['idx'] = idx
                print(format_channel(ch))
        else:
            break

    # Send advert
    print("\n📢 Sending advert...")
    result = await meshcore.commands.send_advert()
    if result.type != EventType.ERROR:
        print("   ✅ Sent")
    else:
        print(f"   ❌ {result.payload}")

    # Start auto message fetching
    await meshcore.start_auto_message_fetching()
    print("📥 Auto message fetching started")

    print("\n" + "="*70)
    print("🎯 MONITORING ALL CHANNELS + ADVERTISEMENTS")
    print(f"💾 Known nodes saved to: {KNOWN_NODES_FILE}")
    print("⌨️  Ctrl+A = Send advert  |  Ctrl+F = Weather to #Public  |  Ctrl+C = Exit")
    if WEATHER_AUTO_SEND_ENABLED:
        print(f"🌤️  Auto weather: every {WEATHER_AUTO_SEND_INTERVAL} min to channel #{WEATHER_AUTO_SEND_CHANNEL}")
    print("="*70 + "\n")

    # Run keyboard listener alongside main loop and auto weather sender
    try:
        await asyncio.gather(
            keyboard_listener(meshcore),
            auto_weather_sender(meshcore),
            asyncio.Event().wait()  # Wait forever
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping...")
    finally:
        for sub in subscriptions:
            meshcore.unsubscribe(sub)
        await meshcore.stop_auto_message_fetching()
        await meshcore.disconnect()
        print("👋 Disconnected")


if __name__ == "__main__":
    asyncio.run(main())