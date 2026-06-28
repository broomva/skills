# OpenRocket Core API Reference

## Rocket Components

All extend `RocketComponent` (tree structure with parent/child relationships).

### Structural

| Class | Description |
|---|---|
| `Rocket` | Top-level container |
| `AxialStage` | Sequential stage |
| `ParallelStage` | Side booster stage |
| `BodyTube` | Main fuselage tube |
| `NoseCone` | Nose cone (ogive, conical, ellipsoid, power series, parabolic, Haack) |
| `Transition` | Shape transition between tubes |
| `CenteringRing` | Motor tube alignment ring |
| `EngineBlock` | Motor thrust surface |
| `InnerTube` | Secondary tubes / motor mounts |
| `BulkHead` | Solid plate |
| `LaunchLug` | Launch rail guide |
| `RailButton` | Rail button guide |

### Fins

| Class | Description |
|---|---|
| `TrapezoidFinSet` | Trapezoidal fins (most common) |
| `EllipticalFinSet` | Elliptical profile fins |
| `FreeformFinSet` | Custom shape fins |
| `TubeFinSet` | Tube-shaped fins |

### Recovery

| Class | Description |
|---|---|
| `Parachute` | Parachute recovery device |
| `Streamer` | Streamer recovery device |
| `ShockCord` | Shock cord |

### Mass

| Class | Description |
|---|---|
| `MassComponent` | Added mass (ballast, electronics) |

## SimulationOptions

50+ configurable parameters on `simulation.getOptions()`:

### Launch Site
- `setLaunchAltitude(double)` — meters above sea level
- `setLaunchLatitude(double)` / `setLaunchLongitude(double)`
- `setLaunchRodLength(double)` — rod length in meters
- `setLaunchRodAngle(double)` — rod angle from vertical (radians)
- `setLaunchRodDirection(double)` — rod compass direction (radians)
- `setLaunchIntoWind(boolean)` — auto-orient rod into wind

### Atmosphere
- `setISAAtmosphere(boolean)` — use International Standard Atmosphere
- `setLaunchTemperature(double)` — custom temperature (K)
- `setLaunchPressure(double)` — custom pressure (Pa)

### Wind
- `getAverageWindModel().setAverage(double)` — average wind speed (m/s)
- `getAverageWindModel().setDirection(double)` — wind direction (radians)
- Multi-level wind model also available

### Simulation
- `setTimeStep(double)` — integration time step (seconds, default 0.05)
- `setSimulationStepperMethodChoice(SimulationStepperMethod)` — RK4 or RK6
- `setMaxSimulationTime(double)` — max sim duration (seconds)
- `setGeodeticComputation(GeodeticComputationStrategy)` — flat/spherical/WGS84

## FlightData Results

After `sim.simulate()`, access via `sim.getSimulatedData()`:

### Summary Values
```java
data.getMaxAltitude()        // meters
data.getMaxVelocity()        // m/s
data.getMaxAcceleration()    // m/s²
data.getMaxMachNumber()      // dimensionless
data.getTimeToApogee()       // seconds
data.getFlightTime()         // seconds
data.getGroundHitVelocity()  // m/s
data.getLaunchRodVelocity()  // m/s
data.getDeploymentVelocity() // m/s
data.getOptimumDelay()       // seconds
```

### Time-Series Data (FlightDataBranch)
```java
FlightDataBranch branch = data.getBranch(0);
branch.get(FlightDataType.TYPE_TIME)
branch.get(FlightDataType.TYPE_ALTITUDE)
branch.get(FlightDataType.TYPE_VELOCITY_TOTAL)
branch.get(FlightDataType.TYPE_ACCELERATION_TOTAL)
branch.get(FlightDataType.TYPE_MACH_NUMBER)
branch.get(FlightDataType.TYPE_THRUST_FORCE)
branch.get(FlightDataType.TYPE_DRAG_FORCE)
branch.get(FlightDataType.TYPE_MASS_ALL)
branch.get(FlightDataType.TYPE_CG_LOCATION)
branch.get(FlightDataType.TYPE_CP_LOCATION)
branch.get(FlightDataType.TYPE_STABILITY)
branch.get(FlightDataType.TYPE_ALTITUDE_ABOVE_SEA)
// ... 50+ data types available
```

### Flight Events
```java
for (FlightEvent event : branch.getEvents()) {
    event.getType()    // LAUNCH, IGNITION, LIFTOFF, LAUNCHROD, BURNOUT,
                       // EJECTION_CHARGE, STAGE_SEPARATION, APOGEE,
                       // RECOVERY_DEVICE_DEPLOYMENT, GROUND_HIT, SIMULATION_END
    event.getTime()    // seconds
    event.getSource()  // RocketComponent that triggered it
}
```

### Multi-Branch (Multi-Stage)
```java
int branches = data.getBranchCount();
// Branch 0 = sustainer, Branch 1+ = separated stages/boosters
for (int i = 0; i < branches; i++) {
    FlightDataBranch branch = data.getBranch(i);
    // process each independently
}
```

## Optimization Framework

Package: `info.openrocket.core.optimization`

### Optimizable Parameters
- `MaximumAltitudeParameter`
- `MaximumVelocityParameter`
- `MaximumAccelerationParameter`
- `GroundHitVelocityParameter`
- `DeploymentVelocityParameter`
- `LandingDistanceParameter`
- `TotalFlightTimeParameter`
- `StabilityParameter`

### Optimization Goals
- `MaximizationGoal` — maximize the parameter
- `MinimizationGoal` — minimize the parameter
- `ValueSeekGoal(target)` — reach a specific target value

### Simulation Modifiers
- `GenericComponentModifier` — modify any component property
- `FlightConfigurationModifier` — modify motor configuration

### Optimizers
- `MultidirectionalSearchOptimizer` — multi-dimensional search
- `GoldenSectionSearchOptimizer` — 1D single-parameter optimization
- `ParallelFunctionCache` — multi-threaded function evaluation

### Usage Pattern
```java
RocketOptimizationFunction func = new RocketOptimizationFunction(
    simulation,
    new MaximumAltitudeParameter(),
    new MaximizationGoal(),
    modifiers,       // List<SimulationModifier>
    domain           // OptimizationDomain
);
// Pass to optimizer, evaluate candidates
```

## File I/O

### Supported Formats
| Format | Extension | Load | Save |
|---|---|---|---|
| OpenRocket | `.ork`, `.ork.gz` | Yes | Yes |
| RockSim | `.rkt` | Yes | No |
| RASAero II | `.rk2` | Yes | No |

### Export Formats
- **OBJ** — 3D printing (`de.javagl:obj`)
- **SVG** — Laser cutting (fin templates)
- **PDF** — Print/export via iTextPDF
- **CSV** — Via CSVSave simulation listener

## Scripting (GraalVM JavaScript)

```java
import info.openrocket.core.scripting.GraalJSScriptEngineFactory;

var factory = new GraalJSScriptEngineFactory();
ScriptEngine engine = factory.getScriptEngine();
// ES2022 with full Java interop
// Access Java: var ArrayList = Java.type('java.util.ArrayList');
```

### Simulation Extensions
Custom listeners hook into the simulation loop:
- `SimulationListener` interface — pre/post step hooks
- `CSVSave` — export data to CSV during simulation
- `PrintSimulation` — log simulation state
- `StopSimulation` — conditional early termination
- `RollControl` — active roll control simulation
- `AirStart` — air-start simulation
- `DampingMoment` — damping moment calculation
