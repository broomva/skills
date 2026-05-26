"""Fleet sync daemon using MQTT with store-and-forward offline support.

Publishes metrics, events, and anomalies. Subscribes to model updates,
config changes, and fleet alerts. Operates fine without connectivity.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class SyncMessage:
    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    qos: int = 1

    def to_json(self) -> str:
        return json.dumps({
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
        })

    @classmethod
    def from_json(cls, data: str) -> SyncMessage:
        d = json.loads(data)
        return cls(topic=d["topic"], payload=d["payload"], timestamp=d.get("timestamp", time.time()))


class SyncDaemon:
    """MQTT-based fleet sync with offline store-and-forward."""

    def __init__(
        self,
        site_id: str,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        queue_dir: Path = Path("data/sync-queue"),
        username: str | None = None,
        password: str | None = None,
    ):
        self.site_id = site_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.queue_dir = queue_dir
        self.username = username
        self.password = password

        self._client = None
        self._connected = False
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False

        self.queue_dir.mkdir(parents=True, exist_ok=True)

    def _topic(self, suffix: str) -> str:
        return f"microgrid/{self.site_id}/{suffix}"

    async def start(self):
        self._running = True
        try:
            await self._connect()
        except Exception as e:
            log.warning("MQTT connect failed, will operate offline: %s", e)
        asyncio.create_task(self._drain_loop())

    async def stop(self):
        self._running = False
        if self._client and self._connected:
            self._client.disconnect()
            self._client.loop_stop()

    async def _connect(self):
        import paho.mqtt.client as mqtt

        self._client = mqtt.Client(client_id=f"microgrid-{self.site_id}", protocol=mqtt.MQTTv311)

        if self.username:
            self._client.username_pw_set(self.username, self.password)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            log.info("MQTT connected to %s:%d", self.broker_host, self.broker_port)
            # Subscribe to inbound topics
            client.subscribe(self._topic("model-update"), qos=1)
            client.subscribe(self._topic("config-change"), qos=1)
            client.subscribe(f"microgrid/fleet/alerts", qos=1)
        else:
            log.warning("MQTT connect failed with rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            log.warning("MQTT disconnected unexpectedly (rc=%d), will retry", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("Invalid MQTT message on %s", msg.topic)
            return

        topic_suffix = msg.topic.replace(f"microgrid/{self.site_id}/", "").replace("microgrid/fleet/", "fleet/")
        for handler in self._handlers.get(topic_suffix, []):
            try:
                handler(topic_suffix, payload)
            except Exception as e:
                log.error("Handler error for %s: %s", topic_suffix, e)

    def on(self, topic_suffix: str, handler: Callable[[str, dict], None]):
        self._handlers.setdefault(topic_suffix, []).append(handler)

    async def publish(self, topic_suffix: str, payload: dict[str, Any], qos: int = 1):
        msg = SyncMessage(topic=self._topic(topic_suffix), payload=payload, qos=qos)

        if self._connected and self._client:
            try:
                result = self._client.publish(msg.topic, msg.to_json().encode("utf-8"), qos=qos)
                if result.rc == 0:
                    return
            except Exception as e:
                log.warning("MQTT publish failed, queuing: %s", e)

        # Store for later
        self._enqueue(msg)

    def _enqueue(self, msg: SyncMessage):
        filename = f"{int(msg.timestamp * 1000)}_{msg.topic.replace('/', '_')}.json"
        filepath = self.queue_dir / filename
        filepath.write_text(msg.to_json())
        log.debug("Queued message: %s", filename)

    async def _drain_loop(self):
        """Periodically try to send queued messages when online."""
        while self._running:
            await asyncio.sleep(30)
            if not self._connected or not self._client:
                continue

            queued = sorted(self.queue_dir.glob("*.json"))
            if not queued:
                continue

            log.info("Draining %d queued messages", len(queued))
            for filepath in queued:
                try:
                    msg = SyncMessage.from_json(filepath.read_text())
                    result = self._client.publish(
                        msg.topic, json.dumps(msg.payload).encode("utf-8"), qos=msg.qos
                    )
                    if result.rc == 0:
                        filepath.unlink()
                    else:
                        break  # stop draining on failure
                except Exception as e:
                    log.warning("Failed to drain %s: %s", filepath.name, e)
                    break

    # Convenience publish methods

    async def publish_metrics(self, metrics: dict[str, Any]):
        await self.publish("metrics", {
            "site_id": self.site_id,
            "metrics": metrics,
            "timestamp": time.time(),
        })

    async def publish_event(self, event_type: str, data: dict[str, Any]):
        await self.publish("events", {
            "site_id": self.site_id,
            "event_type": event_type,
            "data": data,
            "timestamp": time.time(),
        })

    async def publish_anomaly(self, description: str, severity: str, data: dict[str, Any]):
        await self.publish("anomalies", {
            "site_id": self.site_id,
            "description": description,
            "severity": severity,
            "data": data,
            "timestamp": time.time(),
        })

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def queue_depth(self) -> int:
        return len(list(self.queue_dir.glob("*.json")))
