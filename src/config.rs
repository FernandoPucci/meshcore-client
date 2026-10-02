use std::env;

#[derive(Clone, Debug)]
pub struct Config {
    pub serial_port: String,
    pub baudrate: u32,
    pub known_nodes_file: String,
    pub node_name: String,
    pub max_message_length: usize,
    pub metar_api_key: String,
    pub metar_api_base: String,
    pub weather_latitude: f64,
    pub weather_longitude: f64,
    pub weather_api_base: String,
    pub weather_enabled: bool,
    pub weather_interval_minutes: u64,
    pub weather_channel: u8,
    pub telemetry_enabled: bool,
    pub telemetry_interval_minutes: u64,
    pub telemetry_channel: u8,
    pub repeater_password: String,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            serial_port: value("SERIAL_PORT", "/dev/ttyUSB0"),
            baudrate: number("BAUDRATE", 115_200),
            known_nodes_file: value("KNOWN_NODES_FILE", "known_nodes.json"),
            node_name: value("MY_NODE_NAME", "MeshMonitor"),
            max_message_length: number("MAX_MESSAGE_LENGTH", 130),
            metar_api_key: value("METAR_API_KEY", ""),
            metar_api_base: value(
                "METAR_API_BASE",
                "https://api-redemet.decea.mil.br/mensagens/metar",
            ),
            weather_latitude: float("OPEN_METEO_LATITUDE", -21.1775),
            weather_longitude: float("OPEN_METEO_LONGITUDE", -47.8103),
            weather_api_base: value("OPEN_METEO_BASE", "https://api.open-meteo.com/v1/forecast"),
            weather_enabled: boolean("WEATHER_AUTO_SEND_ENABLED", false),
            weather_interval_minutes: number("WEATHER_AUTO_SEND_INTERVAL", 30),
            weather_channel: number("WEATHER_AUTO_SEND_CHANNEL", 0),
            telemetry_enabled: boolean("TELEMETRY_AUTO_SEND_ENABLED", false),
            telemetry_interval_minutes: number("TELEMETRY_AUTO_SEND_INTERVAL", 60),
            telemetry_channel: number("TELEMETRY_AUTO_SEND_CHANNEL", 0),
            repeater_password: value("REPEATER_TELEMETRY_PASSWORD", "CRRP2O26"),
        }
    }
}

fn value(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_string())
}
fn number<T: std::str::FromStr>(name: &str, default: T) -> T {
    env::var(name)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}
fn float(name: &str, default: f64) -> f64 {
    number(name, default)
}
fn boolean(name: &str, default: bool) -> bool {
    env::var(name)
        .map(|v| v.eq_ignore_ascii_case("true"))
        .unwrap_or(default)
}
