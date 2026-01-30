"""
GraphQL over WebSocket Protocol constants and utilities.
Implements graphql-transport-ws protocol.
"""

# Message Types
CONNECTION_INIT = "connection_init"
CONNECTION_ACK = "connection_ack"
PING = "ping"
PONG = "pong"
SUBSCRIBE = "subscribe"
NEXT = "next"
ERROR = "error"
COMPLETE = "complete"

# Legacy protocol (graphql-ws) support if needed
GQL_CONNECTION_INIT = "connection_init"
GQL_CONNECTION_ACK = "connection_ack"
GQL_CONNECTION_ERROR = "connection_error"
GQL_CONNECTION_KEEP_ALIVE = "ka"
GQL_CONNECTION_TERMINATE = "connection_terminate"
GQL_START = "start"
GQL_DATA = "data"
GQL_ERROR = "error"
GQL_COMPLETE = "complete"
GQL_STOP = "stop"

GRAPHQL_TRANSPORT_WS_PROTOCOL = "graphql-transport-ws"
GRAPHQL_WS_PROTOCOL = "graphql-ws"
