from enum import StrEnum


class TransportKind(StrEnum):
    native_ws = "native-ws"
    stdio_bridge = "stdio-bridge"
    remote_ws = "remote-ws"


class ProbeVia(StrEnum):
    health = "health"
    ws_401 = "ws-401"
    ws_auth = "ws-auth"
    tcp = "tcp"
