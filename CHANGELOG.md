# Changelog

## 1.0.0 - Rust

- Remove o monitor Python e as dependências Python do projeto.
- Move o crate para o layout Rust padrão na raiz.
- Mantém o framing serial MeshCore validado em hardware real.
- Portas comandos, contatos, canais, mensagens, advertisements, RX_LOG e telemetria.
- Adiciona consultas METAR e Open-Meteo em Rust.
- Adiciona persistência atômica de nós conhecidos.
- Define Docker e Docker Compose sem Python.
- Adiciona probe de protocolo em `examples/serial_probe.rs`.
