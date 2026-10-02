use crate::error::Result;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct KnownNode {
    pub name: String,
    pub public_key: String,
    pub lat: f64,
    pub lon: f64,
    #[serde(rename = "type")]
    pub node_type: u8,
    pub tx_power: serde_json::Value,
    pub last_seen: i64,
    pub last_rssi: serde_json::Value,
    pub last_snr: serde_json::Value,
    pub last_hops: serde_json::Value,
}

pub type KnownNodes = BTreeMap<String, KnownNode>;

pub fn load(path: &Path) -> Result<KnownNodes> {
    if !path.exists() {
        return Ok(BTreeMap::new());
    }
    let data = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&data).unwrap_or_default())
}

pub fn save(path: &Path, nodes: &KnownNodes) -> Result<()> {
    let tmp = path.with_extension("json.tmp");
    let serialized = serde_json::to_vec_pretty(nodes)?;
    fs::write(&tmp, &serialized)?;
    if let Err(error) = fs::rename(&tmp, path) {
        // Docker file bind mounts cannot be replaced with rename(2). The
        // fallback preserves compatibility with the existing Compose volume.
        if error.raw_os_error() == Some(16) {
            fs::write(path, serialized)?;
            let _ = fs::remove_file(&tmp);
        } else {
            return Err(error.into());
        }
    }
    Ok(())
}
