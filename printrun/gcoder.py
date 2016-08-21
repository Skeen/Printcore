#!/usr/bin/env python
# This file is copied from GCoder.
#
# GCoder is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GCoder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

import sys
import re
import math
import datetime
import logging
from array import array

gcode_parsed_args = ["x", "y", "e", "f", "z", "i", "j"]
gcode_parsed_nonargs = ["g", "t", "m", "n"]
to_parse = "".join(gcode_parsed_args + gcode_parsed_nonargs)
gcode_exp = re.compile("\([^\(\)]*\)|;.*|[/\*].*\n|([%s])([-+]?[0-9]*\.?[0-9]*)" % to_parse)
gcode_strip_comment_exp = re.compile("\([^\(\)]*\)|;.*|[/\*].*\n")
m114_exp = re.compile("\([^\(\)]*\)|[/\*].*\n|([XYZ]):?([-+]?[0-9]*\.?[0-9]*)")
specific_exp = "(?:\([^\(\)]*\))|(?:;.*)|(?:[/\*].*\n)|(%s[-+]?[0-9]*\.?[0-9]*)"
move_gcodes = ["G0", "G1", "G2", "G3"]

class PyLine(object):

    __slots__ = ('x', 'y', 'z', 'e', 'f', 'i', 'j',
                 'raw', 'command', 'is_move',
                 'relative', 'relative_e',
                 'current_x', 'current_y', 'current_z', 'extruding',
                 'current_tool',
                 'gcview_end_vertex')

    def __init__(self, l):
        self.raw = l

    def __getattr__(self, name):
        return None

class PyLightLine(object):

    __slots__ = ('raw', 'command')

    def __init__(self, l):
        self.raw = l

    def __getattr__(self, name):
        return None

try:
    import gcoder_line
    Line = gcoder_line.GLine
    LightLine = gcoder_line.GLightLine
except Exception, e:
    logging.warning("Memory-efficient GCoder implementation unavailable: %s" % e)
    Line = PyLine
    LightLine = PyLightLine

def find_specific_code(line, code):
    exp = specific_exp % code
    bits = [bit for bit in re.findall(exp, line.raw) if bit]
    if not bits: return None
    else: return float(bits[0][1:])

def S(line):
    return find_specific_code(line, "S")

def P(line):
    return find_specific_code(line, "P")

def split(line):
    split_raw = gcode_exp.findall(line.raw.lower())
    if split_raw and split_raw[0][0] == "n":
        del split_raw[0]
    if not split_raw:
        line.command = line.raw
        line.is_move = False
        logging.warning("raw G-Code line \"%s\" could not be parsed" % line.raw)
        return [line.raw]
    command = split_raw[0]
    line.command = command[0].upper() + command[1]
    line.is_move = line.command in move_gcodes
    return split_raw

def parse_coordinates(line, split_raw, imperial = False, force = False):
    # Not a G-line, we don't want to parse its arguments
    if not force and line.command[0] != "G":
        return
    unit_factor = 25.4 if imperial else 1
    for bit in split_raw:
        code = bit[0]
        if code not in gcode_parsed_nonargs and bit[1]:
            setattr(line, code, unit_factor * float(bit[1]))

class GCode(object):

    line_class = Line

    lines = None

    imperial = False
    relative = False
    relative_e = False
    current_tool = 0
    # Home position: current absolute position counted from machine origin
    home_x = 0
    home_y = 0
    home_z = 0
    # Current position: current absolute position counted from machine origin
    current_x = 0
    current_y = 0
    current_z = 0
    # For E this is the absolute position from machine start
    current_e = 0
    total_e = 0
    max_e = 0
    # Current feedrate
    current_f = 0
    # Offset: current offset between the machine origin and the machine current
    # absolute coordinate system (as shifted by G92s)
    offset_x = 0
    offset_y = 0
    offset_z = 0
    offset_e = 0
    # Expected behavior:
    # - G28 X => X axis is homed, offset_x <- 0, current_x <- home_x
    # - G92 Xk => X axis does not move, so current_x does not change
    #             and offset_x <- current_x - k,
    # - absolute G1 Xk => X axis moves, current_x <- offset_x + k
    # How to get...
    # current abs X from machine origin: current_x
    # current abs X in machine current coordinate system: current_x - offset_x

    filament_length = None
    duration = None
    xmin = None
    xmax = None
    ymin = None
    ymax = None
    zmin = None
    zmax = None
    width = None
    depth = None
    height = None

    # abs_x is the current absolute X in machine current coordinate system
    # (after the various G92 transformations) and can be used to store the
    # absolute position of the head at a given time
    def _get_abs_x(self):
        return self.current_x - self.offset_x
    abs_x = property(_get_abs_x)

    def _get_abs_y(self):
        return self.current_y - self.offset_y
    abs_y = property(_get_abs_y)

    def _get_abs_z(self):
        return self.current_z - self.offset_z
    abs_z = property(_get_abs_z)

    def _get_abs_e(self):
        return self.current_e - self.offset_e
    abs_e = property(_get_abs_e)

    def _get_abs_pos(self):
        return (self.abs_x, self.abs_y, self.abs_z)
    abs_pos = property(_get_abs_pos)

    def _get_current_pos(self):
        return (self.current_x, self.current_y, self.current_z)
    current_pos = property(_get_current_pos)

    def _get_home_pos(self):
        return (self.home_x, self.home_y, self.home_z)

    def _set_home_pos(self, home_pos):
        if home_pos:
            self.home_x, self.home_y, self.home_z = home_pos
    home_pos = property(_get_home_pos, _set_home_pos)

    def __init__(self):
        self.lines = [];
        self.home_pos = None;

    def __len__(self):
        return len(self.lines)

    def __iter__(self):
        return self.lines.__iter__()

    def append(self, command, store = True):
        command = command.strip()
        if not command:
            return
        gline = Line(command)
        self._preprocess([gline])
        if store:
            self.lines.append(gline)
        return gline

    def _preprocess(self, lines = None):
        """Checks for imperial/relativeness settings and tool changes"""
        if not lines:
            lines = self.lines

        imperial = self.imperial
        relative = self.relative
        relative_e = self.relative_e
        current_tool = self.current_tool
        current_x = self.current_x
        current_y = self.current_y
        current_z = self.current_z
        offset_x = self.offset_x
        offset_y = self.offset_y
        offset_z = self.offset_z

        # Extrusion computation
        current_e = self.current_e
        offset_e = self.offset_e
        total_e = self.total_e
        max_e = self.max_e

        if self.line_class != Line:
            get_line = lambda l: Line(l.raw)
        else:
            get_line = lambda l: l
        for true_line in lines:
            # # Parse line
            # Use a heavy copy of the light line to preprocess
            line = get_line(true_line)
            split_raw = split(line)
            if line.command:
                # Update properties
                if line.is_move:
                    line.relative = relative
                    line.relative_e = relative_e
                    line.current_tool = current_tool
                elif line.command == "G20":
                    imperial = True
                elif line.command == "G21":
                    imperial = False
                elif line.command == "G90":
                    relative = False
                    relative_e = False
                elif line.command == "G91":
                    relative = True
                    relative_e = True
                elif line.command == "M82":
                    relative_e = False
                elif line.command == "M83":
                    relative_e = True
                elif line.command[0] == "T":
                    current_tool = int(line.command[1:])

                if line.command[0] == "G":
                    parse_coordinates(line, split_raw, imperial)

                # Compute current position
                if line.is_move:
                    x = line.x
                    y = line.y
                    z = line.z

                    if line.f is not None:
                        self.current_f = line.f

                    if line.relative:
                        x = current_x + (x or 0)
                        y = current_y + (y or 0)
                        z = current_z + (z or 0)
                    else:
                        if x is not None: x = x + offset_x
                        if y is not None: y = y + offset_y
                        if z is not None: z = z + offset_z

                    if x is not None: current_x = x
                    if y is not None: current_y = y
                    if z is not None: current_z = z

                elif line.command == "G28":
                    home_all = not any([line.x, line.y, line.z])
                    if home_all or line.x is not None:
                        offset_x = 0
                        current_x = self.home_x
                    if home_all or line.y is not None:
                        offset_y = 0
                        current_y = self.home_y
                    if home_all or line.z is not None:
                        offset_z = 0
                        current_z = self.home_z

                elif line.command == "G92":
                    if line.x is not None: offset_x = current_x - line.x
                    if line.y is not None: offset_y = current_y - line.y
                    if line.z is not None: offset_z = current_z - line.z

                line.current_x = current_x
                line.current_y = current_y
                line.current_z = current_z

                # # Process extrusion
                if line.e is not None:
                    if line.is_move:
                        if line.relative_e:
                            line.extruding = line.e > 0
                            total_e += line.e
                            current_e += line.e
                        else:
                            new_e = line.e + offset_e
                            line.extruding = new_e > current_e
                            total_e += new_e - current_e
                            current_e = new_e
                        max_e = max(max_e, total_e)
                    elif line.command == "G92":
                        offset_e = current_e - line.e
                    elif line.command == "G4":
                        moveduration = P(line)
                        if moveduration:
                            moveduration /= 1000.0
                            totalduration += moveduration
            # ## Loop done

        # Store current status
        self.imperial = imperial
        self.relative = relative
        self.relative_e = relative_e
        self.current_tool = current_tool
        self.current_x = current_x
        self.current_y = current_y
        self.current_z = current_z
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.offset_z = offset_z

        self.current_e = current_e
        self.offset_e = offset_e
        self.max_e = max_e
        self.total_e = total_e

    def estimate_duration(self):
        return self.duration

class LightGCode(GCode):
    line_class = LightLine
