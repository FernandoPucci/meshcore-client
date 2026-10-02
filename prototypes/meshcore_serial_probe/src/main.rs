use std::env;
use std::io;
use std::time::Duration;

const HOST_FRAME_START: u8 = 0x3c;
const DEVICE_FRAME_START: u8 = 0x3e;
const MAX_FRAME_SIZE: usize = 300;
const DEVICE_INFO_RESPONSE: u8 = 0x0d;
const ERROR_RESPONSE: u8 = 0x01;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let port_name = env::args()
        .nth(1)
        .unwrap_or_else(|| "/dev/ttyUSB0".to_string());
    let baudrate = env::args()
        .nth(2)
        .map(|value| value.parse::<u32>())
        .transpose()?
        .unwrap_or(115_200);

    println!("Abrindo {port_name} @ {baudrate}...");
    let mut port = serialport::new(&port_name, baudrate)
        .timeout(Duration::from_secs(3))
        .open()?;

    // CMD_DEVICE_QUERY, matching meshcore_py.commands.device.send_device_query().
    let command = [0x16, 0x03];
    write_frame(&mut *port, &command)?;
    println!("Enviado DEVICE_QUERY: {}", hex(&command));

    let (payload, discarded) = read_frame(&mut *port)?;
    if discarded > 0 {
        println!("Bytes descartados antes do frame: {discarded}");
    }
    println!("Payload recebido ({} bytes): {}", payload.len(), hex(&payload));

    match payload.first().copied() {
        Some(DEVICE_INFO_RESPONSE) => print_device_info(&payload)?,
        Some(ERROR_RESPONSE) => {
            let code = payload.get(1).copied().unwrap_or_default();
            println!("MeshCore retornou ERROR, código: 0x{code:02x}");
        }
        Some(response) => {
            println!("Resposta inesperada: 0x{response:02x}");
        }
        None => println!("Frame vazio recebido"),
    }

    Ok(())
}

fn write_frame(port: &mut dyn serialport::SerialPort, payload: &[u8]) -> io::Result<()> {
    if payload.len() > MAX_FRAME_SIZE {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "payload excede o tamanho máximo do frame",
        ));
    }

    let size = (payload.len() as u16).to_le_bytes();
    let mut frame = Vec::with_capacity(payload.len() + 3);
    frame.push(HOST_FRAME_START);
    frame.extend_from_slice(&size);
    frame.extend_from_slice(payload);
    port.write_all(&frame)?;
    port.flush()
}

fn read_frame(port: &mut dyn serialport::SerialPort) -> io::Result<(Vec<u8>, usize)> {
    let mut byte = [0u8; 1];
    let mut discarded = 0;

    loop {
        port.read_exact(&mut byte)?;
        if byte[0] == DEVICE_FRAME_START {
            break;
        }
        discarded += 1;
    }

    let mut size_bytes = [0u8; 2];
    port.read_exact(&mut size_bytes)?;
    let size = u16::from_le_bytes(size_bytes) as usize;
    if size > MAX_FRAME_SIZE {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("tamanho de frame inválido: {size} bytes"),
        ));
    }

    let mut payload = vec![0u8; size];
    port.read_exact(&mut payload)?;
    Ok((payload, discarded))
}

fn print_device_info(data: &[u8]) -> Result<(), Box<dyn std::error::Error>> {
    if data.len() < 2 {
        return Err("DEVICE_INFO truncado: falta a versão do firmware".into());
    }

    let firmware = data[1];
    println!("DEVICE_INFO recebido: firmware {firmware}");

    if firmware < 3 {
        println!("Firmware anterior à versão 3; campos estendidos não são aplicáveis.");
        return Ok(());
    }
    if data.len() < 80 {
        return Err(format!(
            "DEVICE_INFO truncado: esperados pelo menos 80 bytes, recebidos {}",
            data.len()
        )
        .into());
    }

    let max_contacts = data[2] as u16 * 2;
    let max_channels = data[3];
    let ble_pin = u32::from_le_bytes(data[4..8].try_into()?);
    let fw_build = fixed_string(&data[8..20]);
    let model = fixed_string(&data[20..60]);
    let version = fixed_string(&data[60..80]);

    println!("  max_contacts: {max_contacts}");
    println!("  max_channels: {max_channels}");
    println!("  ble_pin: {ble_pin}");
    println!("  fw_build: {fw_build}");
    println!("  model: {model}");
    println!("  version: {version}");

    if firmware >= 9 && data.len() > 80 {
        println!("  repeat: {}", data[80] != 0);
    }
    if firmware >= 10 && data.len() > 81 {
        println!("  path_hash_mode: {}", data[81]);
    }

    Ok(())
}

fn fixed_string(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes)
        .trim_end_matches('\0')
        .trim()
        .to_string()
}

fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}
