//! Event journal — crash-safe append-only storage.
//!
//! Follows the Lago (Life Agent OS) event-sourcing pattern:
//! every sensor reading and dispatch decision is persisted as an
//! immutable event, enabling replay, audit, and post-hoc analysis.
//!
//! Uses `redb` for transactional, crash-safe embedded storage.

use std::path::Path;

use redb::{Database, ReadableTable, ReadableTableMetadata, TableDefinition};
use tracing::debug;

use crate::devices::SensorReadings;
use crate::dispatch::DispatchDecision;

/// Table for sensor readings, keyed by monotonic event ID.
const READINGS_TABLE: TableDefinition<u64, &[u8]> = TableDefinition::new("readings");

/// Table for dispatch decisions, keyed by monotonic event ID.
const DECISIONS_TABLE: TableDefinition<u64, &[u8]> = TableDefinition::new("decisions");

/// Table for metadata (counters, checkpoints).
const META_TABLE: TableDefinition<&str, u64> = TableDefinition::new("meta");

// ---------------------------------------------------------------------------
// Event journal
// ---------------------------------------------------------------------------

/// Append-only event journal backed by `redb`.
///
/// All events are serialized to JSON and stored with a monotonically
/// increasing sequence number. The journal is crash-safe — partial
/// writes are rolled back on recovery.
pub struct EventJournal {
    db: Database,
}

impl EventJournal {
    /// Open (or create) the event journal at the given path.
    pub fn open(path: &Path) -> anyhow::Result<Self> {
        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let db = Database::create(path)?;

        // Initialize tables on first open
        let write_txn = db.begin_write()?;
        {
            let _readings = write_txn.open_table(READINGS_TABLE)?;
            let _decisions = write_txn.open_table(DECISIONS_TABLE)?;
            let _meta = write_txn.open_table(META_TABLE)?;
        }
        write_txn.commit()?;

        debug!(path = %path.display(), "Event journal opened");
        Ok(Self { db })
    }

    /// Append a sensor readings event to the journal.
    pub fn append_readings(&self, readings: &SensorReadings) -> anyhow::Result<()> {
        let payload = serde_json::to_vec(readings)?;
        let seq = self.next_seq("readings_seq")?;

        let write_txn = self.db.begin_write()?;
        {
            let mut table = write_txn.open_table(READINGS_TABLE)?;
            table.insert(seq, payload.as_slice())?;
        }
        write_txn.commit()?;

        debug!(seq, "Appended sensor readings");
        Ok(())
    }

    /// Append a dispatch decision event to the journal.
    pub fn append_decision(&self, decision: &DispatchDecision) -> anyhow::Result<()> {
        let payload = serde_json::to_vec(decision)?;
        let seq = self.next_seq("decisions_seq")?;

        let write_txn = self.db.begin_write()?;
        {
            let mut table = write_txn.open_table(DECISIONS_TABLE)?;
            table.insert(seq, payload.as_slice())?;
        }
        write_txn.commit()?;

        debug!(seq, "Appended dispatch decision");
        Ok(())
    }

    /// Get the next sequence number for a given counter, incrementing it atomically.
    fn next_seq(&self, counter_key: &str) -> anyhow::Result<u64> {
        let write_txn = self.db.begin_write()?;
        let seq;
        {
            let mut meta = write_txn.open_table(META_TABLE)?;
            let current = meta
                .get(counter_key)?
                .map(|v| v.value())
                .unwrap_or(0);
            seq = current + 1;
            meta.insert(counter_key, seq)?;
        }
        write_txn.commit()?;
        Ok(seq)
    }

    /// Count the number of entries in the readings table.
    #[cfg(test)]
    fn count_readings(&self) -> anyhow::Result<u64> {
        let read_txn = self.db.begin_read()?;
        let table = read_txn.open_table(READINGS_TABLE)?;
        Ok(table.len()?)
    }

    // TODO: Add methods for:
    // - `replay_readings(since: DateTime<Utc>) -> impl Iterator<Item = SensorReadings>`
    // - `replay_decisions(since: DateTime<Utc>) -> impl Iterator<Item = DispatchDecision>`
    // - `compact(keep_last_n: usize)` — remove old events to reclaim disk space
    // - `export_csv(path: &Path)` — export to CSV for external analysis
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::devices::SensorReadings;
    fn temp_journal_path(name: &str) -> std::path::PathBuf {
        std::env::temp_dir()
            .join("microgrid_test_journal")
            .join(format!("{}.redb", name))
    }

    #[test]
    fn test_open_creates_db() {
        let path = temp_journal_path("open_creates");
        // Remove if leftover from a previous run
        let _ = std::fs::remove_file(&path);
        let journal = EventJournal::open(&path);
        assert!(journal.is_ok(), "Journal should open/create successfully");
        assert!(path.exists(), "Database file should exist on disk");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_append_and_sequence() {
        let path = temp_journal_path("append_seq");
        let _ = std::fs::remove_file(&path);
        let journal = EventJournal::open(&path).unwrap();

        // Append 3 readings
        for _ in 0..3 {
            let readings = SensorReadings::default();
            journal.append_readings(&readings).unwrap();
        }

        // Verify sequence numbers increased
        let count = journal.count_readings().unwrap();
        assert_eq!(count, 3, "Should have 3 readings after 3 appends");

        // Append 2 more and verify count grows
        for _ in 0..2 {
            journal.append_readings(&SensorReadings::default()).unwrap();
        }
        let count2 = journal.count_readings().unwrap();
        assert_eq!(count2, 5, "Should have 5 readings total");

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_readings_roundtrip() {
        let path = temp_journal_path("readings_rt");
        let _ = std::fs::remove_file(&path);
        let journal = EventJournal::open(&path).unwrap();

        let readings = SensorReadings {
            solar_kw: 7.5,
            load_kw: 4.2,
            battery_soc_pct: 65.0,
            ..SensorReadings::default()
        };
        journal.append_readings(&readings).unwrap();

        // Read back via raw redb access
        let read_txn = journal.db.begin_read().unwrap();
        let table = read_txn.open_table(READINGS_TABLE).unwrap();
        let entry = table.get(1u64).unwrap().unwrap();
        let stored: SensorReadings = serde_json::from_slice(entry.value()).unwrap();
        assert!((stored.solar_kw - 7.5).abs() < f64::EPSILON);
        assert!((stored.load_kw - 4.2).abs() < f64::EPSILON);
        assert!((stored.battery_soc_pct - 65.0).abs() < f64::EPSILON);

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_crash_safety() {
        let path = temp_journal_path("crash_safety");
        let _ = std::fs::remove_file(&path);
        let journal = EventJournal::open(&path).unwrap();

        // Write 5 entries
        for i in 0..5 {
            let r = SensorReadings {
                solar_kw: i as f64,
                ..SensorReadings::default()
            };
            journal.append_readings(&r).unwrap();
        }
        let count = journal.count_readings().unwrap();
        assert_eq!(count, 5);

        // Drop and reopen — previous writes should still be there (crash-safe)
        drop(journal);
        let journal2 = EventJournal::open(&path).unwrap();
        let count2 = journal2.count_readings().unwrap();
        assert_eq!(count2, 5, "Previous writes should survive reopen (crash-safe)");

        let _ = std::fs::remove_file(&path);
    }
}
