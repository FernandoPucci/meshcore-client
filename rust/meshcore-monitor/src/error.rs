use std::fmt::{Display, Formatter};

#[derive(Debug)]
pub enum Error {
    Io(std::io::Error),
    Serial(serialport::Error),
    Protocol(String),
    Json(serde_json::Error),
    Http(String),
}

impl Display for Error {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "I/O: {error}"),
            Self::Serial(error) => write!(f, "serial: {error}"),
            Self::Protocol(error) => write!(f, "protocol: {error}"),
            Self::Json(error) => write!(f, "JSON: {error}"),
            Self::Http(error) => write!(f, "HTTP: {error}"),
        }
    }
}

impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}
impl From<serialport::Error> for Error {
    fn from(error: serialport::Error) -> Self {
        Self::Serial(error)
    }
}
impl From<serde_json::Error> for Error {
    fn from(error: serde_json::Error) -> Self {
        Self::Json(error)
    }
}

pub type Result<T> = std::result::Result<T, Error>;
