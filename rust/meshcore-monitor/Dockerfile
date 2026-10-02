FROM rust:1.99-bookworm AS builder

WORKDIR /src
COPY rust/meshcore-monitor ./rust/meshcore-monitor
RUN cargo build --release --manifest-path rust/meshcore-monitor/Cargo.toml

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /src/rust/meshcore-monitor/target/release/meshcore-monitor .

ENV RUST_BACKTRACE=1
CMD ["/app/meshcore-monitor"]
