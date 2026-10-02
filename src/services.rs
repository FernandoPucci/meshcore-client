use crate::config::Config;
use crate::error::{Error, Result};
use chrono::Utc;
use chrono_tz::America::Sao_Paulo;
use serde_json::Value;

pub fn fetch_metar(config: &Config, airport: &str) -> Result<Option<String>> {
    let today = date_today();
    let url = format!(
        "{}/{airport}?api_key={}&inicialData={today}&finalData={today}",
        config.metar_api_base,
        urlencoding::encode(&config.metar_api_key)
    );
    let response = ureq::get(&url)
        .call()
        .map_err(|error| Error::Http(error.to_string()))?;
    let body = response
        .into_body()
        .read_to_string()
        .map_err(|error| Error::Http(error.to_string()))?;
    let data: Value = serde_json::from_str(&body)?;
    let mens = data
        .get("data")
        .and_then(|v| v.get("data"))
        .and_then(|v| v.as_array())
        .and_then(|v| v.first())
        .and_then(|v| v.get("mens"))
        .and_then(Value::as_str);
    Ok(mens.map(|value| value.chars().take(config.max_message_length).collect()))
}

pub fn fetch_weather(config: &Config) -> Result<Option<String>> {
    let url = format!("{}?latitude={}&longitude={}&daily=moon_phase&current=is_day,temperature_2m,relative_humidity_2m,weather_code&timezone=America%2FSao_Paulo&forecast_days=1", config.weather_api_base, config.weather_latitude, config.weather_longitude);
    let response = ureq::get(&url)
        .call()
        .map_err(|error| Error::Http(error.to_string()))?;
    let body = response
        .into_body()
        .read_to_string()
        .map_err(|error| Error::Http(error.to_string()))?;
    let data: Value = serde_json::from_str(&body)?;
    let current = data
        .get("current")
        .ok_or_else(|| Error::Protocol("resposta de clima sem current".into()))?;
    let temp = current
        .get("temperature_2m")
        .ok_or_else(|| Error::Protocol("clima sem temperatura".into()))?
        .to_string();
    let humidity = current
        .get("relative_humidity_2m")
        .ok_or_else(|| Error::Protocol("clima sem umidade".into()))?
        .to_string();
    let code = current
        .get("weather_code")
        .and_then(Value::as_i64)
        .unwrap_or(-1);
    let phase = data
        .get("daily")
        .and_then(|v| v.get("moon_phase"))
        .and_then(|v| v.as_array())
        .and_then(|v| v.first())
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let (emoji, description) = weather_description(code);
    let (moon_emoji, moon_description) = moon_description(phase);
    let message = format!("Clima RAO {emoji} {description}\n{temp}°C {humidity}%\n{moon_emoji} {moon_description}\n{}", date_time());
    Ok(Some(
        message.chars().take(config.max_message_length).collect(),
    ))
}

pub fn mention_command(node_name: &str, text: &str) -> Option<String> {
    let marker = format!("@[{} 🤖]", node_name);
    let start = text.to_lowercase().find(&marker.to_lowercase())?;
    Some(text[start + marker.len()..].trim().to_string())
}

fn weather_description(code: i64) -> (&'static str, &'static str) {
    match code {
        0 => ("☀️", "Céu limpo"),
        1 => ("🌤️", "Principalmente limpo"),
        2 => ("⛅", "Parcialmente nublado"),
        3 => ("☁️", "Nublado"),
        45 | 48 => ("🌫️", "Neblina"),
        51..=57 => ("🌦️", "Chuvisco"),
        61..=67 => ("🌧️", "Chuva"),
        71..=77 => ("🌨️", "Neve"),
        80..=82 => ("🌦️", "Pancadas de chuva"),
        85 | 86 => ("🌨️", "Pancadas de neve"),
        95..=99 => ("⛈️", "Tempestade"),
        _ => ("❓", "Desconhecido"),
    }
}
fn moon_description(phase: f64) -> (&'static str, &'static str) {
    match phase {
        p if p < 0.0625 || p >= 0.9375 => ("🌑", "Lua nova"),
        p if p < 0.1875 => ("🌒", "Lua crescente"),
        p if p < 0.3125 => ("🌓", "Quarto crescente"),
        p if p < 0.4375 => ("🌔", "Lua gibosa crescente"),
        p if p < 0.5625 => ("🌕", "Lua cheia"),
        p if p < 0.6875 => ("🌖", "Lua gibosa minguante"),
        p if p < 0.8125 => ("🌗", "Quarto minguante"),
        _ => ("🌘", "Lua minguante"),
    }
}
fn date_today() -> String {
    Utc::now()
        .with_timezone(&Sao_Paulo)
        .format("%Y%m%d")
        .to_string()
}
fn date_time() -> String {
    Utc::now()
        .with_timezone(&Sao_Paulo)
        .format("%H:%M %d/%m/%Y")
        .to_string()
}
