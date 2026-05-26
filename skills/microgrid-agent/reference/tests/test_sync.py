"""
Tests for the fleet sync daemon.

Covers:
- Messages queued to disk when offline
- Queued files are valid JSON
- FleetSync (SyncDaemon) initializes without error

All tests use tmpdir fixtures and require no MQTT broker or network.
"""

import json
import time
from pathlib import Path

import pytest

from src.sync import SyncDaemon, SyncMessage


# ===========================================================================
# SyncMessage Tests
# ===========================================================================

class TestSyncMessage:
    """SyncMessage serialization."""

    def test_to_json_returns_string(self):
        msg = SyncMessage(topic="test/topic", payload={"key": "value"})
        j = msg.to_json()
        assert isinstance(j, str)

    def test_from_json_roundtrip(self):
        """to_json -> from_json should preserve topic and payload."""
        original = SyncMessage(
            topic="microgrid/site-001/metrics",
            payload={"soc": 72.5, "solar_kw": 3.2},
            timestamp=1234567890.0,
        )
        serialized = original.to_json()
        restored = SyncMessage.from_json(serialized)

        assert restored.topic == original.topic
        assert restored.payload == original.payload
        assert restored.timestamp == original.timestamp

    def test_to_json_is_valid_json(self):
        msg = SyncMessage(topic="t", payload={"x": 1})
        parsed = json.loads(msg.to_json())
        assert "topic" in parsed
        assert "payload" in parsed
        assert "timestamp" in parsed


# ===========================================================================
# Queue to Disk Tests
# ===========================================================================

class TestQueueToDisk:
    """Messages written to sync-queue/ when offline."""

    def test_enqueue_creates_file(self, tmp_path):
        """_enqueue should write a JSON file to the queue directory."""
        daemon = SyncDaemon(
            site_id="test-site",
            queue_dir=tmp_path / "sync-queue",
        )
        msg = SyncMessage(
            topic="microgrid/test-site/metrics",
            payload={"test": True},
        )
        daemon._enqueue(msg)

        files = list(daemon.queue_dir.glob("*.json"))
        assert len(files) == 1

    def test_enqueue_multiple_messages(self, tmp_path):
        """Multiple enqueued messages should create multiple files."""
        daemon = SyncDaemon(site_id="test-site", queue_dir=tmp_path / "sq")
        for i in range(5):
            msg = SyncMessage(
                topic=f"microgrid/test-site/event-{i}",
                payload={"index": i},
                timestamp=time.time() + i * 0.001,  # ensure unique filenames
            )
            daemon._enqueue(msg)

        files = list(daemon.queue_dir.glob("*.json"))
        assert len(files) == 5

    def test_queue_depth_property(self, tmp_path):
        """queue_depth should reflect the number of queued files."""
        daemon = SyncDaemon(site_id="test-site", queue_dir=tmp_path / "sq")
        assert daemon.queue_depth == 0

        daemon._enqueue(SyncMessage(topic="t", payload={}))
        assert daemon.queue_depth == 1

        daemon._enqueue(SyncMessage(
            topic="t2", payload={}, timestamp=time.time() + 0.001,
        ))
        assert daemon.queue_depth == 2


class TestQueueFormat:
    """Queued files should be valid JSON."""

    def test_queued_file_is_valid_json(self, tmp_path):
        """Each queued file must parse as valid JSON."""
        daemon = SyncDaemon(site_id="test-site", queue_dir=tmp_path / "sq")
        daemon._enqueue(SyncMessage(
            topic="microgrid/test-site/anomaly",
            payload={"severity": "high", "description": "test"},
        ))

        files = list(daemon.queue_dir.glob("*.json"))
        assert len(files) == 1

        content = files[0].read_text()
        parsed = json.loads(content)
        assert "topic" in parsed
        assert "payload" in parsed
        assert parsed["payload"]["severity"] == "high"

    def test_queued_file_preserves_payload(self, tmp_path):
        """Payload data should be preserved exactly in the queued file."""
        daemon = SyncDaemon(site_id="s1", queue_dir=tmp_path / "sq")
        payload = {
            "soc": 45.2,
            "solar_kw": 3.14,
            "nested": {"a": [1, 2, 3]},
        }
        daemon._enqueue(SyncMessage(topic="t", payload=payload))

        files = list(daemon.queue_dir.glob("*.json"))
        parsed = json.loads(files[0].read_text())
        assert parsed["payload"] == payload

    def test_filename_contains_timestamp(self, tmp_path):
        """Queue filenames should contain the message timestamp."""
        daemon = SyncDaemon(site_id="s1", queue_dir=tmp_path / "sq")
        ts = 1711800000.123
        daemon._enqueue(SyncMessage(topic="t/x", payload={}, timestamp=ts))

        files = list(daemon.queue_dir.glob("*.json"))
        assert len(files) == 1
        filename = files[0].name
        # Timestamp in ms should be in the filename
        assert str(int(ts * 1000)) in filename


# ===========================================================================
# SyncDaemon Initialization
# ===========================================================================

class TestSyncInit:
    """FleetSync (SyncDaemon) initializes without error."""

    def test_init_creates_queue_dir(self, tmp_path):
        """SyncDaemon should create the queue directory on init."""
        queue_dir = tmp_path / "new-queue-dir"
        assert not queue_dir.exists()

        daemon = SyncDaemon(site_id="s1", queue_dir=queue_dir)
        assert queue_dir.exists()
        assert queue_dir.is_dir()

    def test_init_with_defaults(self):
        """SyncDaemon should initialize with default parameters."""
        daemon = SyncDaemon(site_id="test-site")
        assert daemon.site_id == "test-site"
        assert daemon.broker_host == "localhost"
        assert daemon.broker_port == 1883
        assert daemon.is_connected is False

    def test_init_with_auth(self, tmp_path):
        """SyncDaemon should accept MQTT credentials."""
        daemon = SyncDaemon(
            site_id="s1",
            queue_dir=tmp_path / "sq",
            username="user",
            password="pass",
        )
        assert daemon.username == "user"
        assert daemon.password == "pass"

    def test_topic_generation(self, tmp_path):
        """_topic() should produce correct MQTT topic strings."""
        daemon = SyncDaemon(site_id="site-007", queue_dir=tmp_path / "sq")
        assert daemon._topic("metrics") == "microgrid/site-007/metrics"
        assert daemon._topic("events") == "microgrid/site-007/events"

    def test_handler_registration(self, tmp_path):
        """on() should register message handlers."""
        daemon = SyncDaemon(site_id="s1", queue_dir=tmp_path / "sq")

        handler_called = []

        def my_handler(topic, payload):
            handler_called.append((topic, payload))

        daemon.on("test-topic", my_handler)
        assert "test-topic" in daemon._handlers
        assert len(daemon._handlers["test-topic"]) == 1

    def test_initial_not_connected(self, tmp_path):
        """SyncDaemon should not be connected immediately after init."""
        daemon = SyncDaemon(site_id="s1", queue_dir=tmp_path / "sq")
        assert daemon.is_connected is False
