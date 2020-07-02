#!/usr/bin/env python3

# Copyright (C) 2020 Simon Quigley <tsimonq2@lubuntu.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import configparser
import os
from jinja2 import Template


def jinja2_template(src, dest, **kwargs):
    """Wrapper for working with Jinja templates

    src is the Jinja2 template to use, dest is where the rendered file needs
    to go, and any other keywords are passed directly to Template.render()
    """

    # Open the template file as a Jinja2 Template
    with open(src) as templatef:
        template = ""
        for text in templatef.readlines():
            template += text
        template = Template(template)

    # Render the template
    template = template.render(**kwargs)

    # Write the template to the dest
    with open(dest, "w+") as f:
        f.write(template)

    return True

def load_config(path="~/.config/lubuntumetrics"):
    """Load config from ~/.config/lubuntumetrics or given path"""

    # If it contains ~, ensure that's expanded
    if "~" in path:
        path = os.path.expanduser(path)

    # Read from the config file
    config = configparser.ConfigParser()
    config.read(path)

    # Return the config as a dict
    return config
