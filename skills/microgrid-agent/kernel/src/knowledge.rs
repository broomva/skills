//! Knowledge graph — structured information about the microgrid site.
//!
//! Stores and queries relationships between community entities, loads,
//! schedules, and priorities. Uses SQLite with recursive CTEs for
//! graph traversal queries.
//!
//! Example queries:
//! - "What loads are affected if feeder-2 trips?"
//! - "Which loads are priority during a community health emergency?"
//! - "What is the expected load profile on market days?"

use std::path::Path;

use rusqlite::Connection;
use tracing::{debug, info};

// ---------------------------------------------------------------------------
// Knowledge graph
// ---------------------------------------------------------------------------

/// An embedded knowledge graph backed by SQLite.
///
/// Stores entities (loads, feeders, buildings, services) and their
/// relationships as a directed graph. Supports recursive CTE queries
/// for impact analysis and priority resolution.
pub struct KnowledgeGraph {
    conn: tokio::sync::Mutex<Connection>,
}

impl KnowledgeGraph {
    /// Open (or create) the knowledge graph database at the given path.
    pub async fn open(path: &Path) -> anyhow::Result<Self> {
        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let conn = Connection::open(path)?;

        // Initialize schema
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS entities (
                id          TEXT PRIMARY KEY,
                kind        TEXT NOT NULL,  -- 'load', 'feeder', 'building', 'service'
                label       TEXT,
                priority    INTEGER DEFAULT 0,  -- 0=normal, 1=essential, 2=critical
                metadata    TEXT  -- JSON blob for extra attributes
            );

            CREATE TABLE IF NOT EXISTS edges (
                source_id   TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                relation    TEXT NOT NULL,  -- 'feeds', 'contains', 'depends_on', 'serves'
                weight      REAL DEFAULT 1.0,
                PRIMARY KEY (source_id, target_id, relation),
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
            CREATE INDEX IF NOT EXISTS idx_entities_priority ON entities(priority);
            ",
        )?;

        info!(path = %path.display(), "Knowledge graph opened");
        Ok(Self {
            conn: tokio::sync::Mutex::new(conn),
        })
    }

    /// Get all load entity IDs marked as priority (priority >= 1).
    ///
    /// Returns entity IDs sorted by priority descending (critical first).
    pub async fn get_priority_loads(&self) -> Vec<String> {
        let conn = self.conn.lock().await;

        let result: Vec<String> = conn
            .prepare(
                "SELECT id FROM entities WHERE kind = 'load' AND priority >= 1 ORDER BY priority DESC",
            )
            .and_then(|mut stmt| {
                stmt.query_map([], |row| row.get(0))
                    .map(|rows| rows.filter_map(|r| r.ok()).collect())
            })
            .unwrap_or_default();

        debug!(count = result.len(), "Queried priority loads");
        result
    }

    /// Query all entities affected by an event on the given entity.
    ///
    /// Uses a recursive CTE to walk the graph downstream from the
    /// event source, following 'feeds', 'contains', and 'depends_on'
    /// relationships.
    pub async fn query_affected(&self, event_entity_id: &str) -> Vec<String> {
        let conn = self.conn.lock().await;
        let entity_id = event_entity_id.to_string();

        let result: Vec<String> = conn
            .prepare(
                "
                WITH RECURSIVE affected(id, depth) AS (
                    -- Base case: the event source
                    SELECT ?, 0
                    UNION
                    -- Recursive case: follow downstream edges
                    SELECT e.target_id, a.depth + 1
                    FROM affected a
                    JOIN edges e ON e.source_id = a.id
                    WHERE e.relation IN ('feeds', 'contains', 'depends_on')
                      AND a.depth < 10  -- prevent infinite loops
                )
                SELECT DISTINCT id FROM affected WHERE depth > 0
                ORDER BY depth
                ",
            )
            .and_then(|mut stmt| {
                stmt.query_map([&entity_id], |row| row.get(0))
                    .map(|rows| rows.filter_map(|r| r.ok()).collect())
            })
            .unwrap_or_default();

        debug!(
            event = event_entity_id,
            affected_count = result.len(),
            "Queried affected entities"
        );
        result
    }

    // TODO: Add methods for:
    // - `insert_entity(id, kind, label, priority)` — add/update an entity
    // - `insert_edge(source, target, relation, weight)` — add a relationship
    // - `get_load_profile(day_type: &str) -> HashMap<String, f64>` — expected load by entity
    // - `import_from_toml(path: &Path)` — bulk-import site topology from config
    // - `shortest_path(from, to) -> Vec<String>` — find path between entities
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_kg_path(name: &str) -> std::path::PathBuf {
        std::env::temp_dir()
            .join("microgrid_test_kg")
            .join(format!("{}.db", name))
    }

    /// Helper: insert an entity directly via SQL.
    async fn insert_entity(kg: &KnowledgeGraph, id: &str, kind: &str, label: &str, priority: i32) {
        let conn = kg.conn.lock().await;
        conn.execute(
            "INSERT OR REPLACE INTO entities (id, kind, label, priority) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![id, kind, label, priority],
        )
        .unwrap();
    }

    /// Helper: insert an edge directly via SQL.
    async fn insert_edge(kg: &KnowledgeGraph, source: &str, target: &str, relation: &str) {
        let conn = kg.conn.lock().await;
        conn.execute(
            "INSERT OR REPLACE INTO edges (source_id, target_id, relation) VALUES (?1, ?2, ?3)",
            rusqlite::params![source, target, relation],
        )
        .unwrap();
    }

    #[tokio::test]
    async fn test_open_creates_tables() {
        let path = temp_kg_path("open_tables");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();
        let conn = kg.conn.lock().await;
        // Check that tables exist by querying them
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM entities", [], |row| row.get(0))
            .unwrap();
        assert_eq!(count, 0, "Empty knowledge graph should have 0 entities");
        let edge_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM edges", [], |row| row.get(0))
            .unwrap();
        assert_eq!(edge_count, 0, "Empty knowledge graph should have 0 edges");
        drop(conn);
        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_priority_loads_empty() {
        let path = temp_kg_path("priority_empty");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();
        let loads = kg.get_priority_loads().await;
        assert!(loads.is_empty(), "No entities should mean no priority loads");
        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_priority_loads() {
        let path = temp_kg_path("priority_loads");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();

        insert_entity(&kg, "health_post", "load", "Health Post", 2).await;
        insert_entity(&kg, "water_pump", "load", "Water Pump", 1).await;
        insert_entity(&kg, "streetlights", "load", "Street Lights", 0).await; // not priority

        let loads = kg.get_priority_loads().await;
        assert_eq!(loads.len(), 2, "Should have 2 priority loads");
        // Sorted by priority DESC => critical (2) first
        assert_eq!(loads[0], "health_post");
        assert_eq!(loads[1], "water_pump");

        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_query_affected_linear() {
        let path = temp_kg_path("affected_linear");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();

        insert_entity(&kg, "A", "feeder", "Feeder A", 0).await;
        insert_entity(&kg, "B", "load", "Load B", 0).await;
        insert_entity(&kg, "C", "load", "Load C", 0).await;
        insert_edge(&kg, "A", "B", "feeds").await;
        insert_edge(&kg, "B", "C", "feeds").await;

        let affected = kg.query_affected("A").await;
        assert!(affected.contains(&"B".to_string()), "B should be affected by A");
        assert!(affected.contains(&"C".to_string()), "C should be affected by A");
        assert_eq!(affected.len(), 2);

        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_query_affected_branching() {
        let path = temp_kg_path("affected_branch");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();

        insert_entity(&kg, "A", "feeder", "Feeder A", 0).await;
        insert_entity(&kg, "B", "load", "Load B", 0).await;
        insert_entity(&kg, "C", "load", "Load C", 0).await;
        insert_edge(&kg, "A", "B", "feeds").await;
        insert_edge(&kg, "A", "C", "feeds").await;

        let affected = kg.query_affected("A").await;
        assert!(affected.contains(&"B".to_string()));
        assert!(affected.contains(&"C".to_string()));
        assert_eq!(affected.len(), 2);

        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_query_affected_depth_limit() {
        let path = temp_kg_path("affected_depth");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();

        // Create a chain of 15 nodes: N0 -> N1 -> ... -> N14
        // The CTE has depth < 10, so only N1..N10 should be returned
        for i in 0..15 {
            insert_entity(&kg, &format!("N{}", i), "load", &format!("Node {}", i), 0).await;
        }
        for i in 0..14 {
            insert_edge(&kg, &format!("N{}", i), &format!("N{}", i + 1), "feeds").await;
        }

        let affected = kg.query_affected("N0").await;
        // depth < 10 means depths 1..10 => N1..N10 = 10 nodes
        assert!(affected.len() <= 10, "Depth limit should prevent returning more than 10 nodes, got {}", affected.len());
        assert!(affected.contains(&"N1".to_string()), "N1 should be affected");
        assert!(!affected.contains(&"N0".to_string()), "N0 (self) should not be in affected list");

        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_query_affected_no_cycles() {
        let path = temp_kg_path("affected_cycle");
        let _ = std::fs::remove_file(&path);
        let kg = KnowledgeGraph::open(&path).await.unwrap();

        // Create a cycle: A -> B -> A
        insert_entity(&kg, "A", "feeder", "Feeder A", 0).await;
        insert_entity(&kg, "B", "load", "Load B", 0).await;
        insert_edge(&kg, "A", "B", "feeds").await;
        insert_edge(&kg, "B", "A", "feeds").await;

        // This should not hang — the depth limit prevents infinite recursion
        let affected = kg.query_affected("A").await;
        assert!(affected.contains(&"B".to_string()), "B should be in affected list");
        // The cycle will cause A to appear (via B->A at depth 2) but depth < 10 prevents infinite loop
        // The important thing is that this terminates without hanging

        let _ = std::fs::remove_file(&path);
    }
}
