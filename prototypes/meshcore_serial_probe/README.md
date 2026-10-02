# MeshCore Serial Probe

Protótipo mínimo para validar a camada serial do MeshCore sem alterar o dispositivo.

## Execução

```bash
cargo run --release -- /dev/ttyUSB0 115200
```

O programa envia `CMD_DEVICE_QUERY` (`16 03`) no framing usado pelo SDK Python:

```text
Host -> dispositivo: 3c <tamanho uint16 little-endian> <payload>
Dispositivo -> host: 3e <tamanho uint16 little-endian> <payload>
```

Em seguida, valida e decodifica `DEVICE_INFO` (`0x0d`). O protótipo não envia comandos destrutivos nem altera contatos, nome ou configuração.
