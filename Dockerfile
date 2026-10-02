FROM rust:1.99-bookworm AS builder

WORKDIR /src
COPY Cargo.toml Cargo.lock .
COPY src ./src
COPY examples ./examples
RUN cargo build --release --bin meshcore-monitor

FROM debian:bookworm-slim

WORKDIR /app
COPY --from=builder /src/target/release/meshcore-monitor /app/meshcore-monitor

ENV RUST_BACKTRACE=1
CMD ["/app/meshcore-monitor"]
