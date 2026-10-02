# Changelog

## 1.0.1 - Docker serial/storage fix

- Trata `EBUSY` transitório do adaptador serial após o advertisement.
- Permite persistir `known_nodes.json` quando o arquivo é bind-mounted pelo Docker.
- Mantém gravação atômica fora de bind mounts.

## 1.0.0 - Rust

- Remove o monitor Python e as dependências Python do projeto.
- Move o crate para o layout Rust padrão na raiz.
- Mantém o framing serial MeshCore validado em hardware real.
- Portas comandos, contatos, canais, mensagens, advertisements, RX_LOG e telemetria.
- Adiciona consultas METAR e Open-Meteo em Rust.
- Adiciona persistência atômica de nós conhecidos.
- Define Docker e Docker Compose sem Python.
- Adiciona probe de protocolo em `examples/serial_probe.rs`.
