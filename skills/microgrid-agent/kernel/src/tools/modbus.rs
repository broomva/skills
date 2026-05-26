//! Modbus RTU/TCP tool — communication with industrial devices.
//!
//! Wraps `tokio-modbus` for reading/writing Modbus registers on
//! solar inverters, battery management systems, diesel generators,
//! and power meters.

// TODO: Implement ModbusTool struct
//
//   pub struct ModbusTool {
//       /// Serial port or TCP address for the Modbus connection.
//       endpoint: String,
//       /// Modbus slave address.
//       slave_id: u8,
//   }
//
//   impl ModbusTool {
//       pub fn new(endpoint: &str, slave_id: u8) -> Self { ... }
//
//       /// Read holding registers (function code 0x03).
//       pub async fn read_holding_registers(&self, address: u16, count: u16) -> Result<Vec<u16>> { ... }
//
//       /// Write a single register (function code 0x06).
//       pub async fn write_single_register(&self, address: u16, value: u16) -> Result<()> { ... }
//
//       /// Read input registers (function code 0x04) — typically for sensor values.
//       pub async fn read_input_registers(&self, address: u16, count: u16) -> Result<Vec<u16>> { ... }
//   }
//
//   impl Tool for ModbusTool {
//       fn name(&self) -> &str { "modbus" }
//       async fn execute(&self, input: ToolInput) -> Result<ToolOutput> { ... }
//   }
//
// Supported devices (register maps to be defined in config/devices/):
// - Victron Multiplus-II (battery inverter)
// - Fronius Primo (solar inverter)
// - Eastron SDM630 (power meter)
// - Cummins Onan (diesel generator controller)
