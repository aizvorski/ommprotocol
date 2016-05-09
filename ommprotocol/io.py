#!/usr/bin/env python
# -*- coding: utf-8 -*-

#################################################
#           insiliChem OpenMM launcher          #
# --------------------------------------------- #
# By Jaime RGP <jaime@insilichem.com> @ 2016    #
#################################################

"""
ommprotocol.io
--------------

Handle IO stuff
"""
# Python stdlib
import os
import sys
from collections import namedtuple
from argparse import ArgumentParser
# OpenMM and 3rd party helpers
from simtk import unit as u
from simtk.openmm.app import (Topology, PDBFile, ForceField, AmberPrmtopFile,
                              AmberInpcrdFile, CharmmPsfFile, CharmmParameterSet)
from simtk.openmm import XmlSerializer
from parmed.namd import NamdBinCoor, NamdBinVel
from parmed import load_file as parmed_load_file
from openmoltools.utils import create_ffxml_file
import yaml
# Own
from ommprotocol import ommprotocol


class YamlLoader(yaml.Loader):

    """
    YAML Loader with `!include` constructor. Straight from
    https://gist.github.com/joshbode/569627ced3076931b02f
    """

    def __init__(self, stream):
        """Initialise Loader."""

        try:
            self._root = os.path.split(stream.name)[0]
        except AttributeError:
            self._root = os.path.curdir

        yaml.Loader.__init__(stream)

    def construct_include(self, node):
        """Include file referenced at node."""

        filename = os.path.abspath(os.path.join(
            self._root, self.construct_scalar(node)
        ))
        extension = os.path.splitext(filename)[1].lstrip('.')

        with open(filename, 'r') as f:
            if extension in ('yaml', 'yml'):
                return yaml.load(f, self)
            else:
                return ''.join(f.readlines())

YamlLoader.add_constructor('!include', YamlLoader.construct_include)


class MultiFormatLoader(object):

    """
    A base class to load different formats of the same type of file with a
    single method. It is meant to be inherited by handlers that have to deal
    with this situation.

    A basic `load` classmethod is provided to handle the delegation of the
    parsing to the proper loader. To do so, it depends on another classmethod
    `_loaders` that acts as a dict that maps file extensions to handler methods.
    """

    @classmethod
    def load(cls, path, **kwargs):
        name, ext = os.path.splitext(path)
        try:
            return cls._loaders(ext.lsplit('.'))(path, **kwargs)
        except KeyError:
            raise NotImplementedError('Unknown loader for format {}'.format(ext))
        except IOError:
            raise IOError('Could not access file {}'.format(path))

    @classmethod
    def _loaders(cls, ext):
        raise NotImplementedError('Override this method')


class InputContainer(object):

    """
    A base class to storage system parameters in an easy way, such as positions
    or velocities, with optional validation of input data
    """

    def __init__(self, topology=None, positions=None, velocities=None, box=None, **kwargs):
        self._topology = None
        self._positions = None
        self._velocities = None
        self._box = None
        self.topology = topology
        self.positions = positions
        self.velocities = velocities
        self.box = box

    @property
    def topology(self):
        return self._topology

    @topology.setter
    def topology(self, obj):
        self._topology = validate(obj, (Topology, None))

    @property
    def positions(self):
        return self._positions

    @positions.setter
    def positions(self, obj):
        self._positions = validate(obj, (u.Quantity, None))

    @property
    def velocities(self):
        return self._velocities

    @velocities.setter
    def velocities(self, obj):
        self._velocities = validate(obj, (u.Quantity, None))

    @property
    def box(self):
        return self._box

    @box.setter
    def box(self, obj):
        self._box = validate(obj, (u.Quantity, None))

    @property
    def has_topology(self):
        return self.topology is not None

    @property
    def has_positions(self):
        return self.positions is not None

    @property
    def has_velocities(self):
        return self.velocities is not None

    @property
    def has_box(self):
        return self.box is not None


class SystemHandler(MultiFormatLoader, InputContainer):

    """
    Loads an OpenMM topology from `path`

    Parameters
    ----------
    path : str
        Path to desired topology file. Supports pdb, prmtop, psf.
    """

    @classmethod
    def _loaders(cls, ext):
        return {'pdb': cls.from_pdb,
                'prmtop': cls.from_prmtop,
                'top': cls.from_prmtop,
                'psf': cls.from_psf}[ext]

    @classmethod
    def from_pdb(cls, path, forcefields=None):
        """
        Loads topology, positions and, potentially, velocities and vectors,
        from a PDB file

        Parameters
        ----------
        path : str
            Path to PDB file
        forcefields : list of str
            Paths to FFXML and/or FRCMOD forcefields. REQUIRED.

        Returns
        -------
        pdb : SystemHandler
            SystemHandler with topology, positions, and, potentially, velocities and
            box vectors. Forcefields are embedded in the `master` attribute.
        """
        pdb = PDBFile(path)
        box = pdb.topology.getUnitCellDimensions()
        positions = pdb.positions
        velocities = getattr(pdb, 'velocities', None)

        if not forcefields:
            forcefields = ommprotocol.FORCEFIELDS
            print('INFO: Forcefields for PDB not specified. Using default:\n ',
                  ', '.join(forcefields))
        pdb.forcefield = ForceField(*process_forcefield(*forcefields))

        return cls(master=pdb, topology=pdb.topology, positions=positions, velocities=velocities, box=box, path=path)

    @classmethod
    def from_prmtop(cls, path):
        """
        Loads Amber Parm7 parameters and topology file

        Parameters
        ----------
        path : str
            Path to *.prmtop or *.top file

        Returns
        -------
        prmtop : SystemHandler
            SystemHandler with topology
        """
        prmtop = AmberPrmtopFile(path)
        return cls(master=prmtop, topology=prmtop.topology, path=path)

    @classmethod
    def from_psf(cls, path, charmm_parameters=None):
        """
        Loads PSF Charmm structure from `path`. Requires `charmm_parameters`.

        Parameters
        ----------
        path : str
            Path to PSF file
        charmm_parameters : list of str
            Paths to Charmm parameters files, such as *.par or *.str. REQUIRED

        Returns
        -------
        psf : SystemHandler
            SystemHandler with topology. Charmm parameters are embedded in
            the `master` attribute.
        """
        psf = CharmmPsfFile(path)
        if charmm_parameters is None:
            raise ValueError('ERROR: PSF files require charmm_parameters')
        psf.parmset = CharmmParameterSet(*charmm_parameters)
        psf.loadParameters(psf.parmset)
        return cls(master=psf, topology=psf.topology, path=path)

    def __init__(self, master=None, **kwargs):
        InputContainer.__init__(self, **kwargs)
        self.master = master
        self._path = kwargs.get('path')

    def create_system(self, system_options=None):
        """
        Create an OpenMM system for every supported topology file with given system options
        """
        if self.master is None:
            # Probably instantiated from a restart file
            raise ValueError('This instance is not able to create systems.')

        if system_options is None:
            system_options = {}

        if isinstance(self.master, PDBFile):
            if not hasattr(self.master, 'forcefield'):
                raise ValueError('PDB topology files must be instanciated with forcefield paths.')
            return self.master.forcefield.createSystem(self.topology, **system_options)

        if isinstance(self.master, AmberPrmtopFile):
            return self.master.createSystem(**system_options)

        if isinstance(self.master, CharmmPsfFile):
            if not hasattr(self.master, 'parmset'):
                raise ValueError('PSF topology files must be instanciated with Charmm parameters.')
            return self.master.createSystem(self.master.parmset, **system_options)


class Positions(MultiFormatLoader):

    """
    Set of loaders to get position coordinates from file `path`

    Parameters
    ----------
    path : str
        Path to desired coordinates file. Supports pdb, coor, inpcrd.

    Returns
    -------
    positions : simtk.unit.Quantity([atoms,3])
    """

    @classmethod
    def _loaders(cls, ext):
        return {'pdb': cls.from_pdb,
                'coor': cls.from_coor,
                'inpcrd': cls.from_inpcrd,
                'crd': cls.from_inpcrd}[ext]

    @classmethod
    def from_pdb(cls, path):
        pdb = PDBFile(path)
        return pdb.positions

    @classmethod
    def from_coor(cls, path):
        coor = NamdBinCoor.read(path)
        positions = u.Quantity(coor.coordinates[0], unit=u.angstroms)
        return positions

    @classmethod
    def from_inpcrd(cls, path):
        inpcrd = AmberInpcrdFile(path)
        return inpcrd.positions


class Velocities(MultiFormatLoader):

    """
    Set of loaders to get velocities for a given topology from file `path`

    Parameters
    ----------
    path : str
        Path to desired velocities file. Supports vel.

    Returns
    -------
    velocities : simtk.unit.Quantity([atoms,3])
    """

    @classmethod
    def _loaders(cls, ext):
        return {'vel': cls.from_vel}[ext]

    @classmethod
    def from_vel(cls, path):
        vel = NamdBinVel.read(path)
        velocities = u.Quantity(vel.velocities[0], unit=u.angstroms/u.picosecond)
        return velocities


class BoxVectors(MultiFormatLoader):

    """
    Set of loaders to get vectors from file `path`

    Parameters
    ----------
    path : str
        Path to desired velocities file. Supports vel.

    Returns
    -------
    velocities : simtk.unit.Quantity([atoms,3])
    """

    @classmethod
    def _loaders(cls, ext):
        return {'xsc': cls.from_xsc}[ext]

    @classmethod
    def from_xsc(cls, path):
        """ Returns u.Quantity with box vectors from XSC file """

        def parse(path):
            """
            Open and parses an XSC file into its fields

            Parameters
            ----------
            path : str
                Path to XSC file

            Returns
            -------
            namedxsc : namedtuple
                A namedtuple with XSC fields as names
            """
            with open(path) as f:
                lines = f.readlines()
            NamedXsc = namedtuple('NamedXsc', lines[1].split()[1:])
            return NamedXsc(*map(float, lines[2].split()))

        xsc = parse(path)
        box_vectors = u.Quantity(
            [[xsc.a_x, 0, 0], [0, xsc.b_y, 0], [0, 0, xsc.c_z]], unit=u.angstroms)
        return box_vectors


class Restart(MultiFormatLoader, InputContainer):

    """
    Loads a restart file that can contain positions, velocities and box vectors.

    Parameters
    ----------
    path : str
        Restart file

    Returns
    -------
    positions : simtk.unit.Quantity([atoms,3])
    velocities : simtk.unit.Quantity([atoms,3])
    vectors : simtk.unit.Quantity([1,3])
    """

    @classmethod
    def from_xml(cls, path):
        with open(path) as f:
            xml = XmlSerializer.deserialize(f.read())
        positions = xml.getPositions()
        velocities = xml.getVelocities()
        box = xml.getPeriodicBoxVectors()
        return cls(positions=positions, velocities=velocities, box=box)

    @classmethod
    def from_rst(cls, path):
        positions, velocities, box = None, None, None
        rst = parmed_load_file(path)
        positions = u.Quantity(rst.coordinates[0], unit=u.angstrom)
        if rst.hasvels:
            velocities = u.Quantity(rst.velocities[0], unit=u.angstrom/u.picosecond)
        if rst.hasbox:
            vectors = [[rst.cell_lengths[0], 0, 0],
                       [0, rst.cell_lengths[1], 0],
                       [0, 0, rst.cell_lengths[2]]]
            box = u.Quantity(vectors, unit=u.angstrom)
        return cls(positions=positions, velocities=velocities, box=box)

    @classmethod
    def _loaders(cls, ext):
        return {'xml': cls.from_xml,
                'rst': cls.from_rst,
                'restart': cls.from_rst}[ext]


def parse_arguments(argv=None):
    p = ArgumentParser(description='insiliChem.bio OpenMM launcher: '
                       'easy to deploy MD protocols for OpenMM')
    p.add_argument('input', metavar='INPUT FILE', type=str,
                   help='YAML input file')
    p.add_argument('-p', '--platform', type=str, choices=['CPU', 'CUDA', 'OpenCL'],
                   help='Hardware platform to use: CPU, CUDA or OpenCL')
    p.add_argument('-q', '--precision', type=str, choices=['single', 'double', 'mixed'],
                   help='Precision model to use: single, double, or mixed')

    return p.parse_args(argv if argv else sys.argv[1:])

###########################
# Helpers
###########################


def assert_not_exists(path):
    """
    If path exists, modify to add a counter in the filename. Useful
    for preventing accidental overrides. For example, if `file.txt`
    exists, check if `file.1.txt` also exists. Repeat until we find
    a non-existing version, such as `file.12.txt`.

    Parameters
    ----------
    path : str
        Path to be checked

    Returns
    -------
    newpath : str
        A modified version of path with a counter right before the extension.
    """
    name, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(path):
        path = '{}.{}{}'.format(name, i, ext)
        i += 1
    return path


def process_forcefield(*forcefields):
    """
    Given a list of filenames, check which ones are `frcmods`. If so,
    convert them to ffxml. Else, just return them.
    """
    for forcefield in forcefields:
        if forcefield.endswith('.frcmod'):
            yield create_ffxml_file(forcefield)
        else:
            yield forcefield


def validate(object_, type_):
    """
    Make sure `object_` is of type `type_`. Else, raise TypeError.
    """
    if isinstance(object_, type_):
        return object_
    raise TypeError('{} must be instance of {}'.format(object_, type_))

def random_string(length=5):
    return ''.join(choice(ascii_letters) for _ in range(length))