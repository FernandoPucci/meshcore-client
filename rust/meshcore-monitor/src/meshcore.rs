use crate::error::{Error, Result};
use crate::storage::{KnownNode, KnownNodes};
use serialport::SerialPort;
use std::io::{Read, Write};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const HOST_START: u8 = 0x3c;
const DEVICE_START: u8 = 0x3e;
const MAX_FRAME: usize = 300;

#[derive(Debug)]
pub enum Event {
    DeviceInfo(DeviceInfo),
    Contact(Contact),
    ContactsEnd,
    Advertisement { public_key: String },
    NewContact(Contact),
    AdvertPath(Vec<u8>),
    DirectMessage(Message),
    ChannelMessage(Message),
    RxLog(Vec<u8>),
    Log(Vec<u8>),
    Ack(Vec<u8>),
    MessagesWaiting,
    Telemetry(Vec<u8>),
    Ok,
    Error(u8),
    Unknown(Vec<u8>),
}

#[derive(Clone, Debug)]
pub struct DeviceInfo {
    pub firmware: u8,
    pub max_contacts: u16,
    pub max_channels: u8,
    pub model: String,
    pub version: String,
    pub path_hash_mode: Option<u8>,
}

#[derive(Clone, Debug, Default)]
pub struct Contact {
    pub public_key: String,
    pub node_type: u8,
    pub flags: u8,
    pub path: Vec<u8>,
    pub name: String,
    pub last_advert: u32,
    pub lat: f64,
    pub lon: f64,
}

#[derive(Clone, Debug)]
pub struct Message {
    pub channel: Option<u8>,
    pub text: String,
    pub timestamp: u32,
    pub path_len: u8,
    pub snr: Option<f32>,
    pub sender_prefix: Option<String>,
}

#[derive(Clone, Debug, Default)]
pub struct Telemetry {
    pub battery_mv: Option<u16>,
    pub battery_percent: Option<u8>,
    pub temperature: Option<f32>,
}

pub struct MeshCoreClient {
    port: Box<dyn SerialPort>,
}

impl MeshCoreClient {
    pub fn open(path: &str, baudrate: u32) -> Result<Self> {
        let port = serialport::new(path, baudrate)
            .timeout(Duration::from_secs(5))
            .open()?;
        Ok(Self { port })
    }

    pub fn query_device(&mut self) -> Result<DeviceInfo> {
        let payload = self.command(&[0x16, 0x03])?;
        parse_device_info(&payload)
    }

    pub fn set_name(&mut self, name: &str) -> Result<()> {
        let mut cmd = vec![0x08];
        cmd.extend_from_slice(name.as_bytes());
        self.expect_ok(&cmd)
    }

    pub fn send_advert(&mut self) -> Result<()> {
        self.expect_ok(&[0x07])
    }

    pub fn get_channel(&mut self, index: u8) -> Result<Option<(String, Vec<u8>)>> {
        let payload = self.command(&[0x1f, index])?;
        if payload.first() == Some(&0x01) && payload.get(1) == Some(&2) {
            return Ok(None);
        }
        if payload.first() != Some(&0x12) || payload.len() < 50 {
            return Err(Error::Protocol("CHANNEL_INFO inválido".into()));
        }
        Ok(Some((
            fixed_string(&payload[2..34]),
            payload[34..50].to_vec(),
        )))
    }

    pub fn get_contacts(&mut self) -> Result<Vec<Contact>> {
        self.send(&[0x04])?;
        let mut contacts = Vec::new();
        loop {
            let payload = self.read_frame()?;
            match parse_event(payload)? {
                Event::Contact(contact) | Event::NewContact(contact) => contacts.push(contact),
                Event::ContactsEnd => return Ok(contacts),
                Event::Error(code) => {
                    return Err(Error::Protocol(format!("GET_CONTACTS erro {code}")))
                }
                _ => {}
            }
        }
    }

    pub fn remove_contact(&mut self, key: &str) -> Result<()> {
        let mut cmd = vec![0x0f];
        cmd.extend_from_slice(&decode_key(key)?);
        self.expect_ok(&cmd)
    }

    pub fn add_contact(&mut self, contact: &Contact) -> Result<()> {
        let mut cmd = vec![0x09];
        cmd.extend_from_slice(&decode_key(&contact.public_key)?);
        cmd.extend([contact.node_type, contact.flags, 0xff]);
        cmd.extend(std::iter::repeat(0).take(64));
        let mut name = [0u8; 32];
        let bytes = contact.name.as_bytes();
        name[..bytes.len().min(32)].copy_from_slice(&bytes[..bytes.len().min(32)]);
        cmd.extend(name);
        cmd.extend(contact.last_advert.to_le_bytes());
        cmd.extend(((contact.lat * 1_000_000.0).round() as i32).to_le_bytes());
        cmd.extend(((contact.lon * 1_000_000.0).round() as i32).to_le_bytes());
        self.expect_ok(&cmd)
    }

    pub fn send_channel_message(&mut self, channel: u8, text: &str) -> Result<()> {
        let mut cmd = vec![0x03, 0x00, channel];
        cmd.extend(now().to_le_bytes());
        cmd.extend_from_slice(text.as_bytes());
        self.expect_ok(&cmd)
    }

    pub fn send_message(&mut self, key: &str, text: &str) -> Result<()> {
        let full = decode_key(key)?;
        let mut cmd = vec![0x02, 0x00, 0];
        cmd.extend(now().to_le_bytes());
        cmd.extend_from_slice(&full[..6]);
        cmd.extend_from_slice(text.as_bytes());
        let payload = self.command(&cmd)?;
        if payload.first() == Some(&0x06) {
            Ok(())
        } else {
            Err(Error::Protocol("MSG_SENT esperado".into()))
        }
    }

    pub fn request_telemetry(&mut self, key: &str, password: &str) -> Result<Telemetry> {
        let key_bytes = decode_key(key)?;
        let mut login = vec![0x1a];
        login.extend_from_slice(&key_bytes);
        login.extend_from_slice(password.as_bytes());
        let login_response = self.command(&login)?;
        if login_response.first() == Some(&0x01) {
            return Err(Error::Protocol("login no repetidor falhou".into()));
        }
        if login_response.first() == Some(&0x06) {
            let login_event = self.read_frame()?;
            if login_event.first() == Some(&0x86) || login_event.first() == Some(&0x01) {
                return Err(Error::Protocol("login no repetidor falhou".into()));
            }
        }

        let mut request = vec![0x32];
        request.extend_from_slice(&key_bytes);
        request.push(0x03);
        let sent = self.command(&request)?;
        if sent.first() != Some(&0x06) {
            return Err(Error::Protocol("BINARY_REQ não foi aceito".into()));
        }
        for _ in 0..4 {
            let response = self.read_frame()?;
            if response.first() == Some(&0x8b) && response.len() > 7 {
                return parse_lpp(&response[7..]);
            }
            if response.first() == Some(&0x8c) && response.len() > 6 {
                return parse_lpp(&response[6..]);
            }
        }
        Err(Error::Protocol("TELEMETRY_RESPONSE não recebido".into()))
    }

    pub fn next_message(&mut self) -> Result<Option<Event>> {
        self.send(&[0x0a])?;
        let payload = self.read_frame()?;
        match parse_event(payload)? {
            Event::Unknown(data) if data.first() == Some(&0x0a) => Ok(None),
            event => Ok(Some(event)),
        }
    }

    pub fn poll_event(&mut self) -> Result<Event> {
        parse_event(self.read_frame()?)
    }

    fn expect_ok(&mut self, payload: &[u8]) -> Result<()> {
        let response = self.command(payload)?;
        match response.first() {
            Some(0) => Ok(()),
            Some(1) => Err(Error::Protocol(format!(
                "MeshCore erro {}",
                response.get(1).copied().unwrap_or_default()
            ))),
            _ => Err(Error::Protocol("OK inesperado".into())),
        }
    }

    fn command(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        self.send(payload)?;
        self.read_frame()
    }

    fn send(&mut self, payload: &[u8]) -> Result<()> {
        if payload.len() > MAX_FRAME {
            return Err(Error::Protocol("frame excede 300 bytes".into()));
        }
        let mut frame = vec![HOST_START];
        frame.extend((payload.len() as u16).to_le_bytes());
        frame.extend_from_slice(payload);
        self.port.write_all(&frame)?;
        self.port.flush()?;
        Ok(())
    }

    fn read_frame(&mut self) -> Result<Vec<u8>> {
        let mut byte = [0u8; 1];
        loop {
            self.port.read_exact(&mut byte)?;
            if byte[0] == DEVICE_START {
                break;
            }
        }
        let mut size = [0u8; 2];
        self.port.read_exact(&mut size)?;
        let len = u16::from_le_bytes(size) as usize;
        if len > MAX_FRAME {
            return Err(Error::Protocol(format!("frame inválido: {len}")));
        }
        let mut payload = vec![0; len];
        self.port.read_exact(&mut payload)?;
        Ok(payload)
    }
}

pub fn parse_device_info(data: &[u8]) -> Result<DeviceInfo> {
    if data.len() < 80 || data.first() != Some(&0x0d) {
        return Err(Error::Protocol("DEVICE_INFO inválido".into()));
    }
    Ok(DeviceInfo {
        firmware: data[1],
        max_contacts: data[2] as u16 * 2,
        max_channels: data[3],
        model: fixed_string(&data[20..60]),
        version: fixed_string(&data[60..80]),
        path_hash_mode: data.get(81).copied(),
    })
}

pub fn parse_event(data: Vec<u8>) -> Result<Event> {
    let code = *data
        .first()
        .ok_or_else(|| Error::Protocol("frame vazio".into()))?;
    let event = match code {
        0x00 => Event::Ok,
        0x01 => Event::Error(data.get(1).copied().unwrap_or_default()),
        0x02 => Event::Unknown(data),
        0x03 => Event::Contact(parse_contact(&data, false)?),
        0x04 => Event::ContactsEnd,
        0x06 => Event::Unknown(data),
        0x07 => Event::DirectMessage(parse_message(&data, false)?),
        0x08 => Event::ChannelMessage(parse_message(&data, false)?),
        0x10 => Event::DirectMessage(parse_message(&data, true)?),
        0x11 => Event::ChannelMessage(parse_message(&data, true)?),
        0x80 => Event::Advertisement {
            public_key: hex(&data[1..]),
        },
        0x82 => Event::Ack(data[1..].to_vec()),
        0x83 => Event::MessagesWaiting,
        0x88 => Event::RxLog(data[1..].to_vec()),
        0x8a => Event::NewContact(parse_contact(&data, true)?),
        0x8b => Event::Telemetry(data[1..].to_vec()),
        _ => Event::Unknown(data),
    };
    Ok(event)
}

fn parse_contact(data: &[u8], push: bool) -> Result<Contact> {
    let offset = if push { 1 } else { 0 };
    if data.len() < offset + 32 + 1 + 1 + 1 + 64 + 32 + 12 {
        return Err(Error::Protocol("CONTACT truncado".into()));
    }
    let mut pos = offset;
    let key = hex(&data[pos..pos + 32]);
    pos += 32;
    let node_type = data[pos];
    pos += 1;
    let flags = data[pos];
    pos += 1;
    let plen = data[pos];
    pos += 1;
    let path_len = if plen == 255 { 0 } else { plen & 0x3f };
    let path_size = ((plen >> 6) + 1) as usize;
    let path = data[pos..pos + 64].to_vec();
    pos += 64;
    let name = fixed_string(&data[pos..pos + 32]);
    pos += 32;
    let last_advert = u32::from_le_bytes(data[pos..pos + 4].try_into().unwrap());
    pos += 4;
    let lat = i32::from_le_bytes(data[pos..pos + 4].try_into().unwrap()) as f64 / 1e6;
    pos += 4;
    let lon = i32::from_le_bytes(data[pos..pos + 4].try_into().unwrap()) as f64 / 1e6;
    Ok(Contact {
        public_key: key,
        node_type,
        flags,
        path: path[..(path_len as usize * path_size).min(64)].to_vec(),
        name,
        last_advert,
        lat,
        lon,
    })
}

fn parse_message(data: &[u8], v3: bool) -> Result<Message> {
    let mut pos = 1;
    let snr = if v3 {
        let value = data
            .get(pos)
            .copied()
            .ok_or_else(|| Error::Protocol("mensagem truncada".into()))? as i8
            as f32
            / 4.0;
        pos += 3;
        Some(value)
    } else {
        None
    };
    let (channel, sender_prefix) = if data.first() == Some(&0x08) || data.first() == Some(&0x11) {
        let channel = *data
            .get(pos)
            .ok_or_else(|| Error::Protocol("mensagem truncada".into()))?;
        pos += 1;
        (Some(channel), None)
    } else {
        let prefix = hex(data
            .get(pos..pos + 6)
            .ok_or_else(|| Error::Protocol("mensagem truncada".into()))?);
        pos += 6;
        (None, Some(prefix))
    };
    let path_len = *data
        .get(pos)
        .ok_or_else(|| Error::Protocol("mensagem truncada".into()))?;
    pos += 1;
    let text_type = *data
        .get(pos)
        .ok_or_else(|| Error::Protocol("mensagem truncada".into()))?;
    pos += 1;
    let timestamp = u32::from_le_bytes(
        data.get(pos..pos + 4)
            .ok_or_else(|| Error::Protocol("mensagem truncada".into()))?
            .try_into()
            .unwrap(),
    );
    pos += 4;
    if text_type == 2 {
        pos += 4;
    }
    let text = String::from_utf8_lossy(data.get(pos..).unwrap_or_default())
        .trim_matches('\0')
        .to_string();
    Ok(Message {
        channel,
        text,
        timestamp,
        path_len,
        snr,
        sender_prefix,
    })
}

pub fn update_known_node(nodes: &mut KnownNodes, contact: &Contact) {
    nodes.insert(
        contact.public_key.clone(),
        KnownNode {
            name: contact.name.clone(),
            public_key: contact.public_key.clone(),
            lat: contact.lat,
            lon: contact.lon,
            node_type: contact.node_type,
            tx_power: serde_json::Value::String("?".into()),
            last_seen: contact.last_advert as i64,
            last_rssi: serde_json::Value::String("?".into()),
            last_snr: serde_json::Value::String("?".into()),
            last_hops: serde_json::Value::String("?".into()),
        },
    );
}
pub fn now() -> u32 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as u32
}
fn parse_lpp(data: &[u8]) -> Result<Telemetry> {
    let mut result = Telemetry::default();
    let mut pos = 0;
    while pos + 2 <= data.len() {
        let channel_type = data[pos + 1];
        pos += 2;
        match channel_type {
            103 if pos + 2 <= data.len() => {
                result.temperature =
                    Some(i16::from_be_bytes([data[pos], data[pos + 1]]) as f32 / 10.0);
                pos += 2;
            }
            116 if pos + 2 <= data.len() => {
                result.battery_mv = Some(u16::from_be_bytes([data[pos], data[pos + 1]]));
                pos += 2;
            }
            120 if pos < data.len() => {
                result.battery_percent = Some(data[pos]);
                pos += 1;
            }
            100 | 101 | 102 | 115 if pos + 2 <= data.len() => pos += 2,
            _ => break,
        }
    }
    Ok(result)
}
fn decode_key(value: &str) -> Result<Vec<u8>> {
    if value.len() != 64 {
        return Err(Error::Protocol(
            "chave pública deve ter 64 hex chars".into(),
        ));
    }
    (0..32)
        .map(|i| {
            u8::from_str_radix(&value[i * 2..i * 2 + 2], 16)
                .map_err(|_| Error::Protocol("chave pública inválida".into()))
        })
        .collect()
}
fn fixed_string(bytes: &[u8]) -> String {
    let end = bytes
        .iter()
        .position(|byte| *byte == 0)
        .unwrap_or(bytes.len());
    String::from_utf8_lossy(&bytes[..end]).trim().to_string()
}
fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join("")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_device_info_from_hardware_shape() {
        let mut frame = vec![0x0d, 13, 175, 40, 0, 0, 0, 0];
        frame.extend_from_slice(b"14-Aug-2026\0");
        frame.resize(20, 0);
        frame.extend_from_slice(b"Heltec V3\0");
        frame.resize(60, 0);
        frame.extend_from_slice(b"v1.17.1-d929643\0");
        frame.resize(80, 0);
        frame.extend([1, 1]);
        let info = parse_device_info(&frame).unwrap();
        assert_eq!(info.firmware, 13);
        assert_eq!(info.max_contacts, 350);
        assert_eq!(info.model, "Heltec V3");
        assert_eq!(info.path_hash_mode, Some(1));
    }

    #[test]
    fn parses_channel_message() {
        let mut frame = vec![0x08, 0, 0xff, 0];
        frame.extend(1_700_000_000u32.to_le_bytes());
        frame.extend_from_slice(b"hello\0");
        let event = parse_event(frame).unwrap();
        match event {
            Event::ChannelMessage(message) => {
                assert_eq!(message.channel, Some(0));
                assert_eq!(message.text, "hello");
                assert_eq!(message.timestamp, 1_700_000_000);
            }
            _ => panic!("evento inesperado"),
        }
    }

    #[test]
    fn parses_c_string_at_first_nul() {
        assert_eq!(fixed_string(b"Public\0stale"), "Public");
    }
}
