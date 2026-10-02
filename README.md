# MeshCore Monitor

Monitor Rust para nós MeshCore Companion via porta serial.

## Requisitos

- Rust stable 1.99 ou superior para compilação local
- Docker Engine e Docker Compose para execução recomendada
- Acesso do usuário à porta serial (`dialout`)

## Funcionalidades

- Framing serial MeshCore em `115200 8N1`
- Consulta de dispositivo, canais e contatos
- Advertisements e persistência atômica de `known_nodes.json`
- Mensagens diretas e de canais
- Logs RF (`RX_LOG`)
- Consultas METAR e Open-Meteo
- Menções `CLIMA`, `METAR`, `STATUS`, `AJUDA` e `HELP`
- Telemetria binária CayenneLPP de repetidoras
- Imagem Docker sem Python

## Docker

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose logs -f
```

O container utiliza diretamente a porta configurada em `SERIAL_PORT` e grava os nós conhecidos no arquivo montado.

## Execução local

```bash
cargo build --release
cargo run --release
```

Probe somente de protocolo:

```bash
cargo run --release --example serial_probe -- /dev/ttyUSB0 115200
```

## Testes

```bash
cargo fmt --all -- --check
cargo test --all-targets
cargo clippy --all-targets --all-features -- -D warnings
```

## Configuração

As variáveis de ambiente estão documentadas em `.env.example`. O programa carrega `.env` automaticamente quando executado fora do Docker.

## Licença

MIT License.
