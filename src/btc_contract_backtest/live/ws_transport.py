import threading
import logging
from collections import deque
from typing import Any, Union
import websocket

logger = logging.getLogger(__name__)


class DefaultWebsocketTransport:
    """
    A concrete implementation of WebsocketTransport Protocol using websocket-client.
    Provides a simple synchronous recv() mapping from the underlying threaded stream.
    """

    # Maximum messages to buffer. Oldest are dropped when full to prevent OOM.
    MAX_QUEUE_SIZE = 2000

    def __init__(self, url: str, connect_timeout: float = 5.0):
        self.url = url
        # Bounded deque: drops oldest messages when full rather than growing unboundedly.
        self._message_queue: deque[Union[str, bytes]] = deque(
            maxlen=self.MAX_QUEUE_SIZE
        )
        self._error: Exception | None = None
        self._is_closed = False
        self._cond = threading.Condition()
        # Signals that on_open fired (or on_error/on_close fired first).
        self._connected_event = threading.Event()

        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever, daemon=True, name=f"ws-transport-{hash(url)}"
        )
        self._thread.start()

        # Wait for the connection to either open or fail; raises on failure.
        if not self._connected_event.wait(timeout=connect_timeout):
            self._is_closed = True
            raise ConnectionError(
                f"WebSocket did not connect within {connect_timeout}s: {url}"
            )
        # If on_error fired before on_open, re-raise now.
        with self._cond:
            if self._error is not None:
                err = self._error
                self._error = None
                raise err

    def _on_open(self, ws):
        self._connected_event.set()

    def _on_message(self, ws, message):
        with self._cond:
            if len(self._message_queue) == self.MAX_QUEUE_SIZE:
                logger.warning(
                    "ws_transport: message queue full (%d), dropping oldest message",
                    self.MAX_QUEUE_SIZE,
                )
            self._message_queue.append(message)
            self._cond.notify_all()

    def _on_error(self, ws, error):
        with self._cond:
            self._error = (
                error if isinstance(error, Exception) else Exception(str(error))
            )
            self._is_closed = True
            logger.warning("WebsocketTransport error: %s", error)
            self._cond.notify_all()
        # Unblock __init__ wait if we haven't connected yet.
        self._connected_event.set()

    def _on_close(self, ws, close_status_code, close_msg):
        with self._cond:
            self._is_closed = True
            self._cond.notify_all()

    def recv(self, timeout: float = 2.0) -> Union[str, bytes, dict[str, Any]]:
        with self._cond:
            # Wait until a message arrives, an error occurs, or it's closed
            while (
                not self._message_queue and not self._is_closed and self._error is None
            ):
                if not self._cond.wait(timeout):
                    return ""  # Return empty if nothing arrived in timeout to unblock listener loops

            if self._error is not None:
                err = self._error
                self._error = None  # Clear after raising
                raise err
            if self._is_closed and not self._message_queue:
                raise ConnectionError("Websocket transport is closed")

            return self._message_queue.pop(0)

    def close(self) -> None:
        self._is_closed = True
        if self._ws:
            self._ws.close()
        # Wake up any waiting recv() calls
        with self._cond:
            self._cond.notify_all()


def websocket_transport_factory(url: str):
    """Factory function explicitly mapping a URL to a WebsocketTransport implementation."""
    return DefaultWebsocketTransport(url)
