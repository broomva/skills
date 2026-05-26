//! VE.Direct tool — Victron Energy serial protocol.
//!
//! Reads real-time data from Victron Energy devices (MPPT solar charge
//! controllers, BMV battery monitors, Phoenix inverters) via the
//! VE.Direct text protocol over serial (typically /dev/ttyUSB0).

// TODO: Implement VeDirectTool struct
//
//   pub struct VeDirectTool {
//       /// Serial port path (e.g., "/dev/ttyUSB0").
//       port: String,
//       /// Baud rate (VE.Direct uses 19200).
//       baud_rate: u32,
//   }
//
//   impl VeDirectTool {
//       pub fn new(port: &str) -> Self { ... }
//
//       /// Parse a VE.Direct text frame into key-value pairs.
//       /// Frame format: "FIELD\tVALUE\r\n" repeated, terminated by "Checksum\tBYTE".
//       fn parse_frame(data: &[u8]) -> HashMap<String, String> { ... }
//
//       /// Read a complete VE.Direct frame from the serial port.
//       pub async fn read_frame(&self) -> Result<HashMap<String, String>> { ... }
//
//       /// Extract solar power (W) from a VE.Direct frame (PPV field).
//       pub fn solar_power_w(frame: &HashMap<String, String>) -> Option<f64> { ... }
//
//       /// Extract battery voltage (V) from a VE.Direct frame (V field).
//       pub fn battery_voltage_v(frame: &HashMap<String, String>) -> Option<f64> { ... }
//
//       /// Extract battery SOC (%) from a VE.Direct frame (SOC field, BMV only).
//       pub fn battery_soc_pct(frame: &HashMap<String, String>) -> Option<f64> { ... }
//   }
//
//   impl Tool for VeDirectTool {
//       fn name(&self) -> &str { "vedirect" }
//       async fn execute(&self, input: ToolInput) -> Result<ToolOutput> { ... }
//   }
//
// VE.Direct protocol reference:
//   https://www.victronenergy.com/upload/documents/VE.Direct-Protocol-3.33.pdf
// Common fields:
//   V     — Battery voltage (mV)
//   I     — Battery current (mA)
//   VPV   — Panel voltage (mV)
//   PPV   — Panel power (W)
//   CS    — Charge state (0=off, 2=fault, 3=bulk, 4=absorption, 5=float)
//   SOC   — State of charge (‰, BMV only)
//   H19   — Yield total (0.01 kWh)
//   H20   — Yield today (0.01 kWh)
