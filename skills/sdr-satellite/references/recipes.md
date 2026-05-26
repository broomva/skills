# Recipes

Concrete, copy-pasteable. Each recipe lists hardware, software, time budget, and result.

## Recipe 1 — First NOAA APT weather image

**Result:** PNG of weather radar imagery of where you live, taken by NOAA-19 as it passed overhead.
**Time:** 1 afternoon.
**Cost:** ~$50 (dongle + antenna wire).

### Bill of materials
- 1× RTL-SDR v4 USB dongle (~$30 from `rtl-sdr.com`)
- 1× V-dipole antenna: two ~53 cm pieces of wire at 120° angle ($5 in wire + SMA pigtail). Or buy the official RTL-SDR dipole kit ($15).
- macOS / Linux laptop with USB-A or USB-C-to-USB-A adapter

### Software (macOS)
```bash
brew install --cask satdump          # Decoder
brew install gpredict                # Pass predictor
```

### Steps
1. **Plug in the dongle.** Test it sees the airwaves with SDR++:
   ```bash
   brew install --cask sdrpp
   sdrpp                              # Tune to local FM 100.something — you should hear it
   ```
2. **Get current TLEs:**
   ```bash
   curl -s 'https://celestrak.org/NORAD/elements/gp.php?GROUP=noaa&FORMAT=tle' > noaa.tle
   ```
3. **Find the next NOAA-19 pass overhead** in gpredict. Look for elevation ≥30° (low-elevation passes give noisy images).
4. **At AOS (Acquisition of Signal):**
   ```bash
   satdump live_processing noaa_apt_demod ./output_apt \
     --source rtlsdr \
     --frequency 137912500 \
     --samplerate 2400000
   ```
   (NOAA-19 = 137.9125 MHz, NOAA-18 = 137.9125 MHz, NOAA-15 = 137.620 MHz.)
5. **At LOS (Loss of Signal):** Ctrl-C SatDump. PNG outputs are in `./output_apt/`.

### Troubleshooting
- **Noisy image:** antenna polarization wrong. NOAA APT is right-hand circularly polarized; a V-dipole gets some of both. For better images, build a QFH (quadrifilar helix).
- **No signal:** check `rtl_test` to confirm the dongle works; check that the antenna is outside (not in a basement or surrounded by buildings).
- **Image rolling:** clock drift in the RTL-SDR. SatDump's PLL handles this, but if it's bad, use `--ppm 35` to nudge the dongle's clock offset.

## Recipe 2 — Use someone else's ground station (no hardware)

**Result:** Decoded satellite data downloaded from a SatNOGS station that has the antennas you don't.
**Time:** ~10 minutes to schedule + the actual pass duration.
**Cost:** Free.

### Steps
1. **Make a SatNOGS account:** [`network.satnogs.org`](https://network.satnogs.org/).
2. **Pick a satellite:** browse [`db.satnogs.org`](https://db.satnogs.org/). Each entry has frequency, modulation, and which stations have observed it.
3. **Find a station with the right antenna:** [`network.satnogs.org/stations/`](https://network.satnogs.org/stations/). Filter by VHF / UHF / L-band / S-band depending on satellite.
4. **Schedule the observation:** [`network.satnogs.org/observations/new/`](https://network.satnogs.org/observations/new/). Pick station + satellite + pass time.
5. **Wait.** When the pass completes, the station uploads waterfall + IQ + decoded data.
6. **Download via API:**
   ```bash
   curl 'https://network.satnogs.org/api/observations/<obs_id>/' | jq .
   # Has waterfall_url, payload_url, demoddata_url
   ```

## Recipe 3 — Meteor-M LRPT (high-res digital weather)

**Result:** Color weather imagery, much higher resolution than NOAA APT.
**Difference from APT:** digital (QPSK), so you need better SNR — a real antenna helps.

```bash
satdump live_processing meteor_m2-x_lrpt ./output_lrpt \
  --source rtlsdr \
  --frequency 137100000 \
  --samplerate 2400000 \
  --symbolrate 72000 \
  --pll_alpha 0.00788
```

Meteor-M N2: 137.100 MHz. Meteor-M N2-2: 137.900 MHz. Check CelesTrak for current status — these satellites occasionally have transmitter changes.

## Recipe 4 — GOES HRIT (full-disk geostationary Earth)

**Result:** Live full-disk imagery of Earth from a geostationary weather satellite. The picture you see on weather channels.
**Difference:** GOES is at 1.7 GHz and geostationary — you need a small dish (~1 m parabolic or a Wifi-grid antenna) and an LNA. Plus an Airspy or SDRplay (RTL-SDR's bandwidth is too narrow).

Skip if you don't already have a dish and an LNA. But if you do:

```bash
satdump live_processing goes_hrit ./output_goes \
  --source airspy \
  --frequency 1694100000 \
  --samplerate 6000000
```

## Recipe 5 — ISS SSTV (slow-scan TV from astronauts)

ISS occasionally transmits SSTV images on 145.800 MHz (FM) during commemorative events. Check [`amsat.org`](https://www.amsat.org/) for upcoming events.

```bash
satdump live_processing iss_sstv ./output_sstv \
  --source rtlsdr \
  --frequency 145800000 \
  --samplerate 2400000
```

SatDump's SSTV decoder auto-detects modes (Robot, Scottie, Martin, PD).

## Recipe 6 — ADS-B (commercial aircraft positions)

Not a satellite, but the classic SDR "wow" moment, and the dongle does it.

```bash
brew install dump1090-fa
dump1090-fa --interactive
# Open http://localhost:8080 for live map of all aircraft your dongle can hear
```

1090 MHz. Range ~200 nautical miles with a good antenna. Feeds [`adsb-exchange.com`](https://adsb-exchange.com/) if you want to contribute.

## Recipe 7 — Pass prediction in Rust (programmatic)

For a Rust service that needs to know "when does NOAA-19 next pass over Bogotá":

```rust
// Cargo.toml: sgp4 = "1", chrono = "0.4"
use sgp4::Constants;
use chrono::Utc;

let tle_line1 = "1 33591U 09005A   ...";  // From CelesTrak
let tle_line2 = "2 33591  ...";

let elements = sgp4::Elements::from_tle(None, tle_line1.as_bytes(), tle_line2.as_bytes())?;
let constants = Constants::from_elements(&elements)?;

let now = Utc::now();
let minutes_since_epoch = /* compute */;
let prediction = constants.propagate(minutes_since_epoch as f64)?;
// prediction.position is x,y,z TEME (km)
// prediction.velocity is dx,dy,dz TEME (km/s)
```

For az/el conversion (your station's coordinates → satellite az/el), use `satkit` which has built-in ITRF / Geodetic / ENU transforms.

## Recipe 8 — IQ recording for offline analysis

Record raw RF, decode later. Useful for unknown signals or for sharing on `db.satnogs.org`.

```bash
# Record 30 seconds of IQ at 137 MHz, 2.4 MS/s
rtl_sdr -f 137912500 -s 2400000 -n 72000000 capture.iq

# Or with SigMF metadata (the modern way)
satdump record --source rtlsdr --frequency 137912500 --samplerate 2400000 \
  --duration 30 --output capture.sigmf
```

Play back through SatDump or Gqrx with the file source.

## Recipe 9 — Doppler-corrected receive (for LEO satellites)

LEO satellites move fast — frequency shifts ±5 kHz across a pass. SatDump corrects automatically if you give it TLE + your station location:

```bash
satdump live_processing meteor_m2-x_lrpt ./output \
  --source rtlsdr \
  --frequency 137100000 \
  --samplerate 2400000 \
  --doppler_correction \
  --tle "$(curl -s 'https://celestrak.org/NORAD/elements/gp.php?CATNR=40069&FORMAT=tle')" \
  --station_latitude 4.6 \
  --station_longitude -74.0 \
  --station_altitude 2600
```

For custom Rust pipelines: compute Doppler from `satkit`'s relative velocity → adjust SDR center frequency every ~100 ms.

## Recipe 10 — Build your own QFH antenna

The DIY antenna everyone with a 3D printer ends up making. Templates:
- John Coppens's QFH calculator: http://www.jcoppens.com/ant/qfh/calc.en.php
- Specs for 137 MHz NOAA reception: ~530 mm loop circumference, 16 mm pitch
- 3D-printable hub on Printables / Thingiverse — search "QFH 137 MHz"

Build cost: ~$20 in copper wire + PVC + an SMA bulkhead connector. Performance: substantially better than V-dipole, especially at low elevation passes.
