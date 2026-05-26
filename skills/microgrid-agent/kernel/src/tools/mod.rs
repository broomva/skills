//! Tool trait — Praxis pattern for extensible device interfaces.
//!
//! Each tool represents a hardware communication protocol or device
//! driver that can be dynamically loaded and executed. Follows the
//! Life Agent OS Praxis pattern for tool execution.

pub mod modbus;
pub mod vedirect;

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Tool I/O types
// ---------------------------------------------------------------------------

/// Generic input for a tool invocation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInput {
    /// The operation to perform (tool-specific).
    pub operation: String,
    /// Parameters as a JSON value (tool-specific schema).
    pub params: serde_json::Value,
}

/// Generic output from a tool invocation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolOutput {
    /// Whether the operation succeeded.
    pub success: bool,
    /// Result data (tool-specific).
    pub data: serde_json::Value,
    /// Human-readable message.
    pub message: String,
}

// ---------------------------------------------------------------------------
// Tool trait
// ---------------------------------------------------------------------------

/// A tool that can be discovered, described, and executed.
///
/// Follows the Praxis pattern: tools are self-describing and can be
/// invoked generically by the agent runtime. Each tool wraps a specific
/// hardware protocol or device driver.
///
/// Note: Uses `#[allow(async_fn_in_trait)]` because we don't need dyn
/// dispatch for tools at this stage. When dynamic tool discovery is
/// needed, switch to the `async-trait` crate.
#[allow(async_fn_in_trait)]
pub trait Tool: Send + Sync {
    /// The unique name of this tool (e.g., "modbus", "vedirect").
    fn name(&self) -> &str;

    /// Execute the tool with the given input.
    async fn execute(&self, input: ToolInput) -> anyhow::Result<ToolOutput>;
}

// TODO: Add a ToolRegistry for dynamic tool discovery and dispatch.
//
//   pub struct ToolRegistry {
//       tools: HashMap<String, Box<dyn Tool>>,
//   }
//
//   impl ToolRegistry {
//       pub fn register(&mut self, tool: Box<dyn Tool>) { ... }
//       pub fn get(&self, name: &str) -> Option<&dyn Tool> { ... }
//       pub async fn execute(&self, name: &str, input: ToolInput) -> Result<ToolOutput> { ... }
//   }
