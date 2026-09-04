#!/usr/bin/env python3
"""
MeshCore Monitor - Connects to a MeshCore companion node via serial
and displays all received data formatted correctly.
- Monitors all public channels (#)
- Captures advertisements and saves known nodes to file
- Ctrl+A: Send advert
"""
import asyncio
import json
import sys
import time
import termios
import tty
import textwrap
from pathlib import Path
from meshcore import MeshCore, EventType

SERIAL_PORT = "/dev/ttyUSB2"
BAUDRATE = 115200
KNOWN_NODES_FILE = Path("known_nodes.json")

# Display width for boxes
BOX_WIDTH = 72


def wrap_text(text, width=BOX_WIDTH - 4):
    """Wrap text to fit in box."""
    if not text:
        return [""]
    lines = text.split('\n')
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=width) or [""])
    return wrapped


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


async def on_contact_message(event):
    """Handle incoming contact messages (DMs)."""
    msg = event.payload or {}
    text = msg.get('text', '')
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


async def on_channel_message(event):
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


async def keyboard_listener(meshcore):
    """Listen for keyboard input (Ctrl+A)."""
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
    
    # Subscribe to events
    subscriptions = [
        meshcore.subscribe(EventType.CONTACT_MSG_RECV, on_contact_message),
        meshcore.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_message),
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
    print("⌨️  Ctrl+A = Send advert  |  Ctrl+C = Exit")
    print("="*70 + "\n")

    # Run keyboard listener alongside main loop
    try:
        await asyncio.gather(
            keyboard_listener(meshcore),
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