# Where the method applies

For each field: the chain of stages, what should emerge without being drawn, the anchors to
check against, and a negative control. Use it to plan a new simulation or to extend an
existing one.

No numbers are given here on purpose. Fetch each value from its source when you build, store
it with its URL and date, and let the test read it. A value recalled from this file would be
exactly the kind of number the audit exists to catch.

## Extending the cloud chamber

Each of these is one new stage or one replaced approximation in `packages/cloud-chamber`.

| Extension | What emerges | Anchor |
|---|---|---|
| A magnetic field | Tracks curve, tighter as the particle slows; positive and negative particles curve opposite ways | Radius of curvature from momentum, charge and field (analytic) |
| A lead plate across the chamber | Tracks are shorter and more curved below it; some electrons shower | Energy loss in lead from the NIST tables; radiation length from the PDG |
| A clearing field | Old ions are swept out; the background mist thins | Ion drift speed from published mobilities |
| Mie scattering in place of the phase function | Brightness depends on droplet size and viewing angle | A Mie code's published test cases |
| Two-dimensional convection driven by warm side walls | The sensitive layer thins near the walls. The chamber is heated from above and stable, so there is no Rayleigh-Bénard onset to look for | The de Vahl Davis benchmark for a differentially heated cavity; no flow when the walls follow the still-gas profile |
| An expansion (Wilson) chamber | Sharp tracks for a moment after each expansion, then fog | Adiabatic cooling from the expansion ratio; Wilson's thresholds |
| Bremsstrahlung and pair production | Fast electrons radiate; photons convert to electron-positron pairs that curve apart in a field | NIST ESTAR radiative stopping power for the electrons; NIST XCOM cross-sections for the photons |

Other instruments built from the same stages:

| Instrument | Reuses | New stage | Anchor |
|---|---|---|---|
| Geiger counter, as sound | Sources, energy loss | Avalanche and dead time; a click per count | Counts per window are Poisson and intervals are exponential; the dead-time correction formula |
| Bubble chamber | Transport | Nucleation of vapor in superheated liquid | Stopping powers for the liquid; curvature in the field |
| Spark chamber | Transport, ion pairs | Breakdown along the ion trail between plates | Weak: Paschen's law covers a static uniform gap, not a pulsed discharge along a trail. Expect predictions here |
| Scintillator and photomultiplier | Energy loss | Light yield, photon statistics, pulse shape | Published light yields; Poisson width of the photopeak |

## Fluids

- **Chain:** boundaries and forcing; the fluid at rest; collisions or pressure forces between
  parcels (lattice Boltzmann, smoothed particles, or a grid solve); velocity and density
  fields; dye, particles or a schlieren image.
- **Emerges:** boundary layers, vortex streets behind a cylinder, the hydraulic jump, surface
  waves.
- **Anchors:** the Poiseuille profile in a channel or pipe (analytic); Stokes drag on a sphere,
  for a three-dimensional run; the measured Strouhal number against Reynolds number for a
  cylinder (Williamson's 1996 review in the Annual Review of Fluid Mechanics collects the
  curve); the lid-driven cavity benchmark of Ghia, Ghia and Shin; gravity-wave speed in
  shallow water.
- **Conservation:** mass to rounding; momentum as a budget that includes the forces on walls
  and what crosses the inlet and outlet.
- **Control:** fluid at rest with no forcing stays at rest. For a cylinder wake, no shedding
  below the critical Reynolds number.
- **Validity:** the Mach number of a lattice Boltzmann run; the Reynolds number against the
  grid resolution; blockage by the side walls and reflections from the outflow boundary. A
  two-dimensional wake stops matching experiment once the real flow becomes three-dimensional.

## Heat and thermodynamics

- **Chain:** heat sources and boundary temperatures; the material; conduction, convection,
  radiation; the temperature field; a thermal image or a thermometer trace.
- **Emerges:** cooling curves, convection cells, a pressure that follows the gas law in a
  molecular-dynamics box.
- **Anchors:** series solutions of the heat equation for a slab or a sphere; onset of
  Rayleigh-Bénard convection at the critical Rayleigh number; the Maxwell-Boltzmann speed
  distribution and equipartition for hard spheres; steam tables for a working fluid.
- **Conservation:** energy; entropy never decreases in an isolated system.
- **Control:** equal temperatures everywhere give no flow.

## Sound and instruments

This is vinyl's field. The output is a waveform, so the observation stage is a microphone or
a pickup, and the anchors are measured from the rendered samples.

- **Chain:** the player's gesture (pluck, bow, breath, strike); the resonator at rest;
  the excitation mechanism (stick-slip of a bow, a reed's valve, a hammer's felt); the
  vibrating body; radiation to a listening point.
- **Emerges:** the harmonic series of a string and its inharmonicity when the string is stiff;
  a clarinet's weak even harmonics in its low register; the non-harmonic modes of a drum; a
  wolf note; room reverberation.
- **Anchors:** string frequency from length, tension and mass per length; Fletcher's
  inharmonicity formula for piano strings; mode ratios of a circular membrane from the zeros
  of Bessel functions; resonances of a tube with its end correction; Sabine's reverberation
  time for a room.
- **Conservation:** with losses off, the energy of the vibrating body is constant.
- **Control:** no excitation gives silence, to the last sample.
- **Validity:** a finite-difference string or membrane has numerical dispersion that detunes
  the upper partials. Run the refinement check in method.md section 4 before comparing
  partials with theory.

## Light and optics

- **Chain:** the light source and its spectrum; the optical elements and their refractive
  index data; refraction, reflection, interference, diffraction; rays or a field; a sensor
  with a spectral response.
- **Emerges:** rainbows and their secondary bow, soap-film colours, caustics at the bottom of
  a pool, the Airy pattern of a lens, chromatic aberration.
- **Anchors:** the rainbow angle from measured dispersion of water (refractiveindex.info
  stores the data with sources); thin-film reflectance from the Fresnel equations; the Airy
  disc radius for a circular aperture; Mie theory for a sphere.
- **Conservation:** reflected plus transmitted plus absorbed power equals incident power.
- **Control:** an element whose index equals its surroundings deviates nothing.

## Orbits and mechanics

- **Chain:** initial positions and velocities; the bodies and their masses; gravity or
  contact forces; trajectories under a symplectic integrator; a view from a chosen frame.
- **Emerges:** Kepler's laws, resonances, tides, precession, the chaos of three bodies.
- **Anchors:** JPL Horizons ephemerides; Kepler's third law; the analytic two-body solution;
  the period of a pendulum including its amplitude correction.
- **Conservation:** energy, momentum and angular momentum. Report the drift.
- **Control:** a single body with no force moves in a straight line.

## Electricity and electromagnetism

- **Chain:** sources (voltages, currents, antennas); the components or the medium; circuit
  laws or Maxwell's equations on a grid; voltages, currents or fields; an oscilloscope trace
  or a field image.
- **Emerges:** resonance, standing waves, skin effect, the cutoff of a waveguide, antenna
  patterns.
- **Anchors:** analytic RC, RL and RLC responses; the same circuit in SPICE; waveguide cutoff
  frequencies; Mie scattering for a sphere on an FDTD grid.
- **Conservation:** charge at every node; Poynting's theorem on the grid.
- **Control:** no source gives zero field everywhere.

## Chemistry and reaction-diffusion

- **Chain:** initial concentrations; the reactor geometry; rate laws and diffusion;
  concentration fields; a colour map through an indicator's absorption.
- **Emerges:** Turing spots and stripes, travelling fronts, the oscillations of the
  Belousov-Zhabotinsky reaction, flame fronts.
- **Anchors:** the pattern wavelength from linear stability analysis; front speed from the
  Fisher-KPP result; a stochastic (Gillespie) run against the rate equations at large
  molecule counts; published rate constants (NIST Chemical Kinetics Database).
- **Conservation:** atoms of each element in a closed reactor. The usual pattern-forming models
  (Gray-Scott, the Brusselator, the Oregonator) are open, with feed and removal terms, so check
  the budget including those terms.
- **Control:** a uniform steady state with no perturbation stays uniform.

## Neurons and physiology

- **Chain:** injected current or synaptic input; the membrane and its channels; channel
  gating kinetics; membrane voltage along the cell; an electrode trace.
- **Emerges:** the action potential and its threshold, the refractory period, propagation
  speed along an axon, bursting.
- **Anchors:** the Hodgkin and Huxley 1952 squid-axon parameters and their published traces;
  ModelDB reference implementations; cable-theory length and time constants.
- **Conservation:** charge across the membrane.
- **Control:** no input, resting potential holds.

## Structures and materials

- **Chain:** loads; the body's geometry and material constants; elasticity (finite elements
  or a mass-spring lattice), contact, fracture; displacement and stress; a deformed shape or
  a strain map.
- **Emerges:** buckling, resonance and mode shapes, crack paths, the pile angle of grains.
- **Anchors:** Euler-Bernoulli beam deflections and natural frequencies; Euler's buckling
  load; Hertz contact; material constants from a handbook. For grains, the angle of repose
  and the Janssen saturation of pressure in a silo are measured per material.
- **Conservation:** energy with damping off; force balance at rest.
- **Control:** no load, no displacement.

## Where the laws are themselves models

Traffic, epidemics, markets, flocks, crowds. The rules are stylised, not laws, so:

- Most claims will be `prediction` and `convention`. Write them that way.
- Anchors are weaker but exist: the final-size equation of an SIR epidemic, the fundamental
  diagram of traffic flow, a conserved count of agents or of money.
- A control still applies: no infected agents, no epidemic.

The method still pays here, because it forces the split between what was checked and what was
assumed. It does not make the output a forecast.
