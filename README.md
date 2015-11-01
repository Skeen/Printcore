Printcore is a library that makes writing reprap hosts easy

## Linux
### Ubuntu/Debian

You can run Printrun directly from source, as there are no packages available yet. Fetch and install the dependencies using

1. `sudo apt-get install python-serial python2.7 git`

Clone the repository

`git clone https://github.com/Skeen/Printrun.git`

and you can start using Printcore from the Printrun directory created by the git clone command.

## USING PRINTCORE

See the bottom of printcore.py for a simple command-line sender, or the following code example:

```python
#to send a file of gcode to the printer
from printrun.printcore import printcore
from printrun import gcoder
p=printcore('/dev/ttyUSB0',115200) # or p.printcore('COM3',115200) on Windows
gcode=[i.strip() for i in open('filename.gcode')] # or pass in your own array of gcode lines instead of reading from a file
gcode = gcoder.LightGCode(gcode)
p.startprint(gcode) # this will start a print

#If you need to interact with the printer:
p.send_now("M105") # this will send M105 immediately, ahead of the rest of the print
p.pause() # use these to pause/resume the current print
p.resume()
p.disconnect() # this is how you disconnect from the printer once you are done. This will also stop running prints.
```

# LICENSE

```
Printrun is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Printrun is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Printrun.  If not, see <http://www.gnu.org/licenses/>.
```

All scripts should contain this license note, if not, feel free to ask us. Please note that files where it is difficult to state this license note (such as images) are distributed under the same terms.
