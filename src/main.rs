use meshcore_monitor::config::Config;
use meshcore_monitor::error::Result;
use meshcore_monitor::meshcore::{update_known_node, Event, MeshCoreClient};
use meshcore_monitor::services;
use meshcore_monitor::storage;
use std::path::Path;
use std::thread;
use std::time::{Duration, Instant};

fn main() -> Result<()> {
    dotenvy::dotenv().ok();
    let config = Config::from_env();
    let path = Path::new(&config.known_nodes_file);
    let mut known_nodes = storage::load(path)?;
    println!(
        "Conectando ao MeshCore em {} @ {}...",
        config.serial_port, config.baudrate
    );
    let mut client = MeshCoreClient::open(&config.serial_port, config.baudrate)?;
    let info = client.query_device()?;
    println!(
        "Conectado: {} | {} | firmware {}",
        info.model, info.version, info.firmware
    );

    for index in 0..info.max_channels.min(40) {
        if let Some((name, _secret)) = client.get_channel(index)? {
            if !name.is_empty() {
                println!("Canal [{index}] {name}");
            }
        }
    }
    client.send_advert()?;
    println!("Advert enviado");
    std::thread::sleep(Duration::from_millis(500));
    let contacts = client.get_contacts()?;
    for contact in &contacts {
        update_known_node(&mut known_nodes, contact);
    }
    storage::save(path, &known_nodes)?;
    println!(
        "{} contatos processados; monitorando eventos",
        contacts.len()
    );

    if config.telemetry_enabled {
        send_repeater_telemetry(&mut client, &config, &known_nodes)?;
    }

    if config.weather_enabled {
        if let Some(message) = services::fetch_weather(&config)? {
            client.send_channel_message(config.weather_channel, &message)?;
        }
    }

    let mut last_telemetry = Instant::now();
    loop {
        if config.telemetry_enabled
            && last_telemetry.elapsed()
                >= Duration::from_secs(config.telemetry_interval_minutes * 60)
        {
            send_repeater_telemetry(&mut client, &config, &known_nodes)?;
            last_telemetry = Instant::now();
        }
        match client.next_message()? {
            Some(Event::DirectMessage(message)) => {
                println!(
                    "DM [{}]: {}",
                    message.sender_prefix.clone().unwrap_or_default(),
                    message.text
                );
                if let Some(airport) = parse_metar(&message.text) {
                    if let Some(response) = services::fetch_metar(&config, &airport)? {
                        if let Some(sender) = message.sender_prefix {
                            println!(
                                "METAR para {} pronto; prefixo de resposta: {}",
                                airport, sender
                            );
                        }
                        println!("{}", response);
                    }
                }
            }
            Some(Event::ChannelMessage(message)) => {
                println!(
                    "CANAL #{}: {}",
                    message.channel.unwrap_or_default(),
                    message.text
                );
                if let Some(command) = services::mention_command(&config.node_name, &message.text) {
                    if command.eq_ignore_ascii_case("clima") {
                        if let Some(response) = services::fetch_weather(&config)? {
                            client.send_channel_message(
                                message.channel.unwrap_or_default(),
                                &response,
                            )?;
                        }
                    } else if command.eq_ignore_ascii_case("ajuda")
                        || command.eq_ignore_ascii_case("help")
                    {
                        let help = format!(
                            "Comandos @[{} 🤖]:\n-CLIMA\n-METAR <ICAO>\n-STATUS <PUBKEY>",
                            config.node_name
                        );
                        client.send_channel_message(message.channel.unwrap_or_default(), &help)?;
                    } else if let Some(key) = parse_status(&command) {
                        let repeater_name = known_nodes
                            .get(&key)
                            .map(|node| node.name.as_str())
                            .unwrap_or("Repetidora");
                        match client.request_telemetry(&key, &config.repeater_password) {
                            Ok(data) => {
                                let battery = data
                                    .battery_percentage()
                                    .map(|v| format!("{v}%"))
                                    .unwrap_or_else(|| "N/A".into());
                                let temperature = data
                                    .temperature
                                    .map(|v| format!("{v:.0}C"))
                                    .unwrap_or_else(|| "N/A".into());
                                client.send_channel_message(
                                    message.channel.unwrap_or_default(),
                                    &format!("{}\n🔋{} 🌡️{}", repeater_name, battery, temperature),
                                )?;
                            }
                            Err(error) => client.send_channel_message(
                                message.channel.unwrap_or_default(),
                                &format!("{}\n❌{}", repeater_name, error),
                            )?,
                        }
                    } else if let Some(airport) = parse_metar(&command) {
                        if let Some(response) = services::fetch_metar(&config, &airport)? {
                            client.send_channel_message(
                                message.channel.unwrap_or_default(),
                                &response,
                            )?;
                        }
                    }
                }
            }
            Some(Event::Advertisement { public_key }) => println!("ADVERTISEMENT: {public_key}"),
            Some(Event::NewContact(contact)) => {
                println!("NOVO CONTATO: {} ({})", contact.name, contact.public_key);
                update_known_node(&mut known_nodes, &contact);
                storage::save(path, &known_nodes)?;
            }
            Some(Event::RxLog(data)) => println!("RX_LOG: {} bytes", data.len()),
            Some(event) => println!("EVENTO: {event:?}"),
            None => thread::sleep(Duration::from_millis(500)),
        }
    }
}

fn parse_metar(text: &str) -> Option<String> {
    let words: Vec<_> = text.split_whitespace().collect();
    let index = words
        .iter()
        .position(|word| word.eq_ignore_ascii_case("metar"))?;
    let airport = words.get(index + 1)?.to_ascii_uppercase();
    (airport.len() == 4 && airport.chars().all(|c| c.is_ascii_alphanumeric())).then_some(airport)
}

fn parse_status(text: &str) -> Option<String> {
    let words: Vec<_> = text.split_whitespace().collect();
    let index = words
        .iter()
        .position(|word| word.eq_ignore_ascii_case("status"))?;
    let key = words.get(index + 1)?.to_ascii_lowercase();
    (key.len() == 64 && key.chars().all(|c| c.is_ascii_hexdigit())).then_some(key)
}

fn send_repeater_telemetry(
    client: &mut MeshCoreClient,
    config: &Config,
    nodes: &meshcore_monitor::storage::KnownNodes,
) -> Result<()> {
    for node in nodes.values().filter(|node| node.node_type == 2) {
        match client.request_telemetry(&node.public_key, &config.repeater_password) {
            Ok(data) => {
                let battery = data
                    .battery_percentage()
                    .map(|v| format!("{v}%"))
                    .unwrap_or_else(|| "N/A".into());
                let temperature = data
                    .temperature
                    .map(|v| format!("{v:.0}C"))
                    .unwrap_or_else(|| "N/A".into());
                let message = format!("{}\n🔋{} 🌡️{}", node.name, battery, temperature);
                client.send_channel_message(config.telemetry_channel, &message)?;
            }
            Err(error) => eprintln!("telemetria {}: {error}", node.name),
        }
    }
    Ok(())
}
