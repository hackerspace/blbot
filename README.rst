blbot
=====

Hackerspace status bot running on Raspberry Pi, updating IRC topic on state changes.

Schematic::

     7 (output)
     |
    _|_+
   _\_/_  (led)
     |
    _|_
   |560|  (560 Ohm resistor)
   |___|
     |
     o----9 (GND)
     |
     o
    --- switch
     o
     |
     11 (input with internall pull-up resistor)

Requirements:
 - Python 2.7+
 - python-twisted 12.1.0+
 - python-twisted-words 12.1.0+
 - python-twisted-web


Usage:
 - copy `settings.py` to `local_settings.py` and edit according to your needs
 - run as `python blbot.py` (in screen with tee for best performance)
