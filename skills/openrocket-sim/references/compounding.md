# Compounding Strategies for OpenRocket

## 1. Headless CLI Tool

Wrap the `core` module as a command-line tool for batch simulation:

```bash
# Target UX
rocket-sim run design.ork --config motor=C6-5 --output results.csv
rocket-sim sweep design.ork --param fin_count=3,4,5 --param rod_angle=0,5,10
rocket-sim optimize design.ork --target max_altitude --vary fin_span,nose_length
```

Implementation approach:
- Single Java main class using `GeneralRocketLoader` + `Simulation`
- picocli or JCommander for CLI parsing
- JSON/CSV output for pipeline integration
- Build as GraalVM native image for fast startup

## 2. AI-Driven Design Optimization

Use LLM to guide the optimization loop:

```
LLM proposes design changes → OpenRocket simulates → Results fed back → LLM refines
```

- Start with an agent that reads FlightData results and proposes SimulationModifier adjustments
- Use the built-in `RocketOptimizationFunction` + `MultidirectionalSearchOptimizer` as the inner loop
- LLM acts as the outer loop: selecting which parameters to optimize, interpreting trade-offs, adjusting goals
- Can express design intent in natural language: "maximize altitude while keeping stability margin above 1.5 cal"

## 3. Design Space Exploration

Parameter sweep across multiple dimensions to map Pareto frontiers:

- **Variables**: nose cone shape, fin geometry (span, chord, sweep), body tube diameter/length, motor selection, material choices
- **Objectives**: max altitude vs. stability margin, max altitude vs. ground hit velocity, flight time vs. landing distance
- **Output**: JSON dataset suitable for visualization (scatter plots, Pareto curves)

Use `ParallelFunctionCache` for multi-threaded evaluation. Each simulation takes ~100ms, enabling sweeps of 10K+ configurations.

## 4. Modern Web UI / API

Replace or complement the Swing GUI:

```
Next.js frontend ← REST/gRPC → Java API server ← OpenRocket core
```

- Spring Boot or Javalin thin API layer around the core module
- Endpoints: `POST /simulate`, `POST /optimize`, `GET /components`
- WebSocket for streaming simulation progress
- React/Three.js for 3D rocket visualization
- Alternative: GraalVM native image as a serverless function

## 5. Rocket Design Language (DSL)

YAML/TOML-based rocket specification that compiles to .ork:

```yaml
rocket:
  name: "Alpha III Clone"
  stages:
    - name: sustainer
      components:
        - type: nose_cone
          shape: ogive
          length: 0.07
          diameter: 0.025
        - type: body_tube
          length: 0.20
          diameter: 0.025
          children:
            - type: trapezoidal_fins
              count: 3
              root_chord: 0.05
              tip_chord: 0.03
              span: 0.05
              sweep: 0.01
            - type: inner_tube
              motor: C6-5
            - type: parachute
              diameter: 0.30
              deploy_event: ejection_charge
  simulation:
    atmosphere: ISA
    rod_length: 1.0
    time_step: 0.05
```

Benefits: version-controlled rocket designs, diff-friendly, CI/CD for rocket design validation.

## 6. Manufacturing Pipeline

Automated export after optimization converges:

```
Optimized design → OBJ export (3D print nose cone, fins)
                 → SVG export (laser cut fin templates)
                 → PDF (parts list, assembly guide)
                 → BOM (bill of materials with supplier links)
```

Hook into the file I/O APIs — OBJ via `de.javagl:obj`, SVG via core's SVG exporter, PDF via iTextPDF.

## 7. Simulation-as-a-Service

Containerize for cloud batch processing:

```dockerfile
FROM eclipse-temurin:17-jre
COPY OpenRocket-shadow.jar /app/
ENTRYPOINT ["java", "-jar", "/app/OpenRocket-shadow.jar"]
```

- Expose via REST API
- Queue-based batch processing (SQS/Redis → worker pool)
- Store results in S3/database
- Use for Monte Carlo analysis (1000+ runs with randomized wind/atmosphere)

## 8. Integration with Physical Sensors

Post-flight analysis pipeline:

```
Altimeter data (CSV) → Compare with simulation → Calibrate drag model → Re-simulate
```

- Import real flight data alongside simulated data
- Compute residuals to improve aerodynamic models
- Feed back into design optimization loop

## Architecture for Compounding

```
┌─────────────────────────────────────────────┐
│  Agent Layer (LLM + Skills)                 │
│  - Natural language design intent           │
│  - Trade-off reasoning                      │
│  - Design review and suggestions            │
├─────────────────────────────────────────────┤
│  CLI / API Layer                            │
│  - rocket-sim CLI tool                      │
│  - REST API (Spring Boot / Javalin)         │
│  - Rocket DSL compiler                      │
├─────────────────────────────────────────────┤
│  OpenRocket Core (Headless)                 │
│  - Component tree builder                   │
│  - 6DOF simulation engine                   │
│  - Optimization framework                   │
│  - File I/O (.ork, .rkt, OBJ, SVG)         │
├─────────────────────────────────────────────┤
│  Output Layer                               │
│  - FlightData (JSON/CSV)                    │
│  - Manufacturing files (OBJ, SVG, PDF)      │
│  - Visualization (charts, 3D renders)       │
└─────────────────────────────────────────────┘
```
