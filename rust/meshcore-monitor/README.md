# MeshCore Monitor em Rust

Migração modular do monitor Python para Rust.

## Estado atual

- Transporte serial MeshCore validado em hardware real.
- Framing `0x3c/0x3e` com tamanho `uint16 little-endian`.
- Consulta de informações do dispositivo.
- Leitura de canais e contatos.
- Envio de advertisement.
- Polling de mensagens diretas e de canais.
- Persistência atômica de `known_nodes.json`.
- Consultas METAR e Open-Meteo.
- Menções `CLIMA`, `METAR`, `AJUDA` e `HELP` em canais.

## Execução

Na raiz do projeto:

```bash
cargo run --release --manifest-path rust/meshcore-monitor/Cargo.toml
```

O `.env` existente é carregado automaticamente. Também é possível executar com variáveis de ambiente explícitas.

O processo não limpa contatos do hardware durante a inicialização.
