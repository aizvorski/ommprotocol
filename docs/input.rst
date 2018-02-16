.. _input:

=======================
OMMProtocol input files
=======================

OMMProtocol is designed with a strong focus on reproducibility. As a result, the input file contains all the necessary details to run a whole simulation. OMMProtocol input files are written with Jinja-enhanced YAML files and look like this:

::

    # Protocol for implicit solvent (implicit.yaml)

    # input
    topology: example.pdb
    forcefield: [amber99sbildn.xml, amber99_obc.xml] # only for PDB

    # output
    project_name: sys
    outputpath: output
    report: True
    report_every: 1000
    trajectory: DCD
    trajectory_every: 2000
    trajectory_new_every: 1e6
    restart: rs
    restart_every: 1e6
    save_state_at_end: True

    # hardware
    platform: CUDA
    platform_properties:
        Precision: mixed

    # conditions
    integrator: LangevinIntegrator
    temperature: 300
    friction: 0.1
    timestep: 1.0
    barostat: False
    pressure: 1.01325
    barostat_interval: 100
    minimization_max_iterations: 1000

    # OpenMM system options
    nonbondedMethod: CutoffNonPeriodic
    nonbondedCutoff: 1.0 # nm
    constraints: HBonds
    rigidWater: True
    extra_system_options:
        implicitSolvent: GBn2

    stages:
    -   name: implicit
        temperature: 300 # K
        minimization: True
        md_steps: 250e6
        trajectory: DCD
        trajectory_step: 2000

There's two main parts in these files:

* Top-level parameters: listed in next section, they are common for all stages
* ``stages``: Contains a list with all the stages to be simulated in the requested order. Each stage can override one or more global parameter(s), if needed.

Provided examples
-----------------

OMMProtocol ships with some `ready-to-use example protocols <https://github.com/insilichem/ommprotocol/tree/master/examples>`_, which can be used as a template to create a custom one. Most of the time you will only need to change the ``topology`` and ``positions`` keys, detailed in the next section. Available examples:

- `standard.yaml <https://github.com/insilichem/ommprotocol/blob/master/examples/standard.yaml>`_: The protocol used in most of our solvated protein simulations, such as in [Lur]. It includes a progressive solvent relaxation step, followed by a simulated annealing from 100 to 300K, ending with a long production stage.
- `standard_jinja.yaml <https://github.com/insilichem/ommprotocol/blob/master/examples/standard_jinja.yaml>`_: Same as previous one, but the simulated annealing stages are described with a Jinja loop for a cleaner result.
- `implicit.yaml <https://github.com/insilichem/ommprotocol/blob/master/examples/implicit.yaml>`_: Same parameters as ``standard.yaml``, but optimized for implicit solvent conditions in a single stage (no need for solvent relaxation).
- `test.yaml <https://github.com/insilichem/ommprotocol/blob/master/examples/test.yaml>`_: Protocol meant to debug a problematic simulation (those that end in ``Particle position is NaN``, for example) by dumping states and trajectories every 10 steps. It runs very slow and consumes lots of disk space!
- `simple.yaml <https://github.com/insilichem/ommprotocol/blob/master/examples/simple.yaml>`_: Toy example to show the simplest protocol implementable in OMMProtocol.


Top-level parameters
--------------------

All the parametes are optional except stated otherwise.

Input options
.............

- ``topology``: Main input file. Should contain, at least, the topology, but it can also contain positions, velocities, PBC vectors, forcefields... Required.
- ``positions``: File with the initial coordinates of the system. Overrides those in topology, if needed. Required if the topology does not provide positions.
- ``velocities``: File containing the initial velocities of this stage. If not set, they will be set to the requested temperature.
- ``box_vectors``: File with replacement periodic box vectors, instead of those in the topology or positions file. Supported file types: XSC.
- ``checkpoint``: Restart simulation from this file. It can provide one or more of the options above.
- ``forcefield``: Which forcefields should be used, if not provided in topology. Required for PDB topologies. OpenMM ships with `these forcefields <https://github.com/pandegroup/openmm/tree/master/wrappers/python/simtk/openmm/app/data>`_.
- ``charmm_parameters``: CHARMM forcefield. Required for PSF topologies.

Since several types of files can provide the same type of data (positions, vectors...), there is an established order of precedence. ``topology < checkpoint < positions & velocities < box``. The only keys out of this chain are``forcefield`` and ``charmm_parameters``, which are only required for the specified types of topology.

::

    topology  <---------| forcefield (PDB only)
    ^                   | charmm_parameters (PSF only)
    [checkpoint]
    ^
    positions (required if not provided above), [velocities]
    ^
    [box]


Output options
..............

- ``project_name``: Name for this simulation. Optional. Defaults to a random 5-character string.
- ``outputpath``: Path to output folder. If relative, it'll be relative to input file. Optional. Defaults to ``.`` (directory where the input file is located).
- ``report``: True for live report of progress. Defaults to True.
- ``report_every``: Update interval of live progress reports. Defaults to 1000 steps.
- ``trajectory``: Output format of trajectory file, if desired. Defaults to None (no trajectory will be written).
- ``trajectory_every``: Write trajectory every n steps. Defaults to 2000 steps.
- ``trajectory_new_every``: Create a new file for trajectory every n steps. Defaults to 1,000,000 steps.
- ``restart``: Output format for restart/checkpoint files, if desired. Defaults to None (no checkpoint will be generated).
- ``restart_every``: Write restart format every n steps. Defaults to 1,000,000 steps.
- ``save_state_at_end``: Whether to save the state of the simulation at the end of every stage. Defaults to True.
- ``attempt_rescue``: Try to dump the simulation state into a file if an exception occurs. Defaults to True.

General conditions of simulation
................................

- ``minimization``: If *True*, minimize before simulating a MD stage. Defaults to False.
- ``steps``: Number of MD steps to simulate. If 0, no MD will take place. Defaults to 0.
- ``timestep``: Integration timestep, in fs. Defaults to 1.0.
- ``temperature``: In Kelvin. Defaults to 300.
- ``barostat``: *True* for NPT, *False* for NVT. Defaults to False.
- ``pressure``: In bar. Only used if barostat is *True*. Defaults to 1.01325.
- ``barostat_interval``: Update interval of barostat, in steps. Defaults to 25.
- ``restrained_atoms``, `constrained_atoms`: Parts of the system that should remain restrained (a ``k*((x-x0)^2+(y-y0)^2+(z-z0)^2)`` force is applied to minimize movement) or constrained (no movement at all) during the simulation. Supports ``mdtraj``'s `DSL queries <http://mdtraj.org/latest/atom_selection.html>`_ or a list of 0-based atom indices. Default to None (no freezing).
- ``restraint_strength``: If restraints are in use, the strength of the applied force in kJ/mol. Defaults to 5.0.
- ``integrator``: Which integrator should be used. Langevin by default.
- ``friction``: Friction coefficient for integrator, if needed. In 1/ps. Defaults to 1.0.
- ``minimization_tolerance``: Threshold value minimization should converge to. Defaults to 10 kJ/mole.
- ``minimization_max_iterations``: Limit minimization iterations up to this value. If zero, don't limit. Defaults to 10000.

OpenMM system parameters
........................

These parameters directly correspond to those used in OpenMM. Their default values will be inherited as a result. For example, if the topology chose is PDB, the system will be created out of the  ``forcefield`` object, whose default values are stated `here <http://docs.openmm.org/7.1.0/api-python/generated/simtk.openmm.app.forcefield.ForceField.html#simtk.openmm.app.forcefield.ForceField.createSystem>`_. For other topologies, check the loaders `here <http://docs.openmm.org/7.1.0/api-python/app.html#loaders-and-setup>`_.

Most common parameters are summarized here.

- ``nonbondedMethod``: The method to use for nonbonded interactions. Choose between *NoCutoff* (default), *CutoffNonPeriodic*, *CutoffPeriodic*, *Ewald*, *PME*.
- ``nonbondedCutoff``: The cutoff distance to use for nonbonded interactions, in nm. Defaults to 1.0.
- ``constraints``:  Specifies which bonds angles should be implemented with constraints. Choose between *None* (default), *HBonds*, *AllBonds*, *HAngles*.
- ``rigidWater``: If True (default), water molecules will be fully rigid regardless of the value passed for the constraints argument
- ``removeCMMotion``: Whether to remove center of mass motion during simulation. Defaults to *True*.
- ``extra_system_options``: A sub-dict with additional keywords that might be supported by the `.createSystem` method of the topology in use. Check the `OpenMM docs <http://docs.openmm.org/7.1.0/api-python/app.html#loaders-and-setup>`_ to know which ones to use.

Hardware options
................

- ``platform``: Which platform to use: *CPU*, *CUDA*, *OpenCL*. If not set, OpenMM will choose the fastest available.
- ``platform_properties``: A sub-dict of keyworkds to configure the chosen platform. Check the `OpenMM docs <http://docs.openmm.org/7.1.0/api-python/generated/simtk.openmm.openmm.Platform.html#simtk.openmm.openmm.Platform>`_ to know the supported values. Please notice all values must be strings, even booleans and ints; as a result, you should quote the values like this ``'true'``.