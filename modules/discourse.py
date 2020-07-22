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

import datetime
import requests_cache
import time
from modules.utilities import *
from os import getenv, makedirs, path
from pydiscourse import DiscourseClient

requests_cache.install_cache("discourse", backend="sqlite", expire_after=300)


class DiscourseModule:
    """Discourse module for the Metrics program"""

    def __init__(self):
        self.name = "Discourse"

    def _auth_discourse_server(self):
        """Authenticate to Discourse

        This uses the API_SITE, API_USER, and API_KEY env vars.
        """
        # Load the config, so we can store secrets outside of env vars
        config = load_config()
        in_conf = "discourse" in config

        # Load the needed secrets either from the config file if it exists
        # or the env var if it's defined (which takes precedence)
        site = getenv("DISCOURSE_API_SITE") or (in_conf and config["discourse"]["site"])
        user = getenv("DISCOURSE_API_USER") or (in_conf and config["discourse"]["user"])
        key = getenv("DISCOURSE_API_KEY") or (in_conf and config["discourse"]["key"])
        for envvar in [site, user, key]:
            if not envvar:
                raise ValueError("DISCOURSE_API_SITE, DISCOURSE_API_USER, and",
                                 "DISCOURSE_API_KEY must be defined")
        # Authenticate to the server
        server = DiscourseClient(site, api_username=user, api_key=key)

        return server

    def _get_data(self):
        """Get the data from Discourse

        This function returns six distinct values as one list:

        [open_support, total_support, percent_support, open_all, total_all,
         percent_all]
        """

        # Authenticate to the server
        server = self._auth_discourse_server()

        # Initialize the data
        data = [0, 0, 0, 0, 0, 0]

        for category in server.categories():
            # We are limited to 30 topics per page, so we have to loop until
            # there are no more topics
            page = 0
            on_page = 1
            c_id = category["id"]

            while on_page > 0:
                # Get a list of all the topics to then iterate on
                page_data = server.category_topics(category_id=c_id, page=page)
                topics = page_data["topic_list"]["topics"]
                on_page = len(topics)
                page += 1

                print("Working on " + category["name"])
                for topic in topics:
                    # Increment total_all
                    data[4] += 1

                    # If it's open, increment open_all
                    if not topic["closed"]:
                        data[3] += 1

                    # If the topic is in Support, repeat
                    if category["name"] == "Support":
                        data[1] += 1
                        if not topic["closed"]:
                            data[0] += 1

        # Calculate the percentages
        data[2] = ((data[0] / data[1]) * 100)
        data[5] = ((data[3] / data[4]) * 100)

        return data

    def sqlite_setup(self):
        """Initially set up the table for usage in SQLite

        This returns a str which will then be executed in our SQLite db

        Here is the "discourse" table layout:
         - date is the primary key, and it is the Unix timestamp as an int
         - open_support is the number of open topics in the Support category
         - total_support is the number of total topics in the Support category
         - percent_support is ((open_support / total_support) * 100)
         - open_all is the number of open topics on the Discourse instance
         - total_all is the number of total topics on the Discourse instance
         - percent_all is ((open_all / total_all) * 100)
        """

        command = "CREATE TABLE IF NOT EXISTS discourse (date INTEGER PRIMARY"
        command += " KEY, open_support INTEGER, total_support INTEGER, "
        command += "percent_support INTEGER, open_all INTEGER, total_all "
        command += "INTEGER, percent_all INTEGER);"

        return command

    def sqlite_add(self):
        """Add data to the SQLite db

        This retrieves the current data from the Jenkins server, and returns a
        str which will then be executed in our SQLite db
        """

        # Match the variable names with the column names in the db
        data = tuple(self._get_data())
        date = "strftime('%s', 'now')"

        # Craft the str
        print(data)
        command = "INSERT INTO discourse VALUES ("
        command += "{}, {}, {}, {}, {}, {}, {});".format(date, *data)

        return command

    def sqlite_time_range(self, days):
        """Get the rows which have been inserted given days

        e.g. if days is 180, it gets all of the values which have been
        inserted in the past 180 days.

        Note: this just returns the command to be ran, it doesn't actually run
        """

        now = datetime.datetime.now()
        timedelta = datetime.timedelta(days=days)
        unix_time = int(time.mktime((now - timedelta).timetuple()))

        command = "SELECT * FROM discourse WHERE date > %s;" % unix_time

        return command

    def render_template(self, days, data):
        """Render a template with days in the filename, given the data

        The above function sqlite_time_range() is ran on the database with
        some predetermined date ranges. This function actually interprets that
        data, uses Jinja2 to magically render a template, and voila.
        """

        # Initialize a (softly) ephemeral dict to store data
        discourse = dict()
        keys = ["date", "open_support", "total_support", "percent_support",
                "open_all", "total_all", "percent_all"]

        # Use a lambda to map the data into a dict with the keys
        for row in data:
            print(row)
            _data = {keys[x] : row[x] for x in range(len(row))}

            # Add our ephemeral dict to the master dict, and create the key if
            # it doesn't already exist
            for key in _data.keys():
                if key in discourse:
                    discourse[key].append(_data[key])
                else:
                    discourse[key] = [_data[key]]

        data = discourse

        # Get human-readable averages and throw it in a dict
        average = {}
        for datatype in keys:
            try:
                num = sum(data[datatype]) / len(data[datatype])
                num = format(num, ".1f")
            except ZeroDivisionError:
                num = 0
            average[datatype] = num

        # Assign data to the dict Jinja2 is actually going to use
        discourse = {keys[x] : zip(data["date"], data[keys[x]]) for x in range(len(keys))}

        # Make the output dir if it doesn't already exist
        if not path.exists("output"):
            makedirs("output")

        src = path.join("templates", "discourse.html")
        dest = path.join("output", "discourse_%sdays.html" % days)
        jinja2_template(src, dest, discourse=discourse, average=average,
                        days=days)

        # Return the averages for use in the summary
        r_data = []
        del keys[0]
        for key in keys:
            r_data.append(average[key])

        return tuple(r_data)
