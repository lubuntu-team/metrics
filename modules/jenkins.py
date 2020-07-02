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
from jenkinsapi.custom_exceptions import NoBuildData
from jenkinsapi.jenkins import Jenkins
from modules.utilities import *
from os import getenv, makedirs, path

requests_cache.install_cache("jenkins", backend="sqlite", expire_after=300)


class JenkinsModule:
    """Jenkins module for the Metrics program"""

    def __init__(self):
        self.name = "Jenkins"

    def _auth_jenkins_server(self):
        """Authenticate to the Jenkins server

        This uses the API_SITE, API_USER, and API_KEY env vars.
        """
        # Load the config, so we can store secrets outside of env vars
        config = load_config()
        in_conf = "jenkins" in config

        # Load the needed secrets either from the config file if it exists
        # or the env var if it's defined (which takes precedence)
        site = getenv("API_SITE") or (in_conf and config["jenkins"]["site"])
        user = getenv("API_USER") or (in_conf and config["jenkins"]["user"])
        key = getenv("API_KEY") or (in_conf and config["jenkins"]["key"])
        for envvar in [site, user, key]:
            if not envvar:
                raise ValueError("API_SITE, API_USER, and API_KEY must be",
                                 "defined")
        # Authenticate to the server
        server = Jenkins(site, username=user, password=key)

        return server

    def _get_data(self):
        """Get the data from the Jenkins server

        This function returns three distinct values as one list:

        [nonpassing, failing, total]
        """

        # Authenticate to the server
        server = self._auth_jenkins_server()

        # Initialize the data, and get the total jobs on the server
        data = [0, 0, len(server.jobs.keys())]

        # jenkinsapi has a built-in method for iterating on jobs
        # val will always be a jenkins Job class
        for val in server.jobs.itervalues():
            # If we come across a job that has no build, make it a SUCCESS
            # The goal of this is to identify problematic jobs, and jobs with
            # no existing builds aren't necessarily problematic (yet)
            try:
                status = val.get_last_build().get_status() or \
                        val.get_last_completed_build().get_status()
            except NoBuildData:
                status = "SUCCESS"

            # If it's not successful, add it to nonpassing, since failing is
            # reserved for jobs with the specific status of FAILURE
            if status != "SUCCESS":
                data[0] += 1

                if status == "FAILURE":
                    data[1] += 1

        return data

    def sqlite_setup(self):
        """Initially set up the table for usage in SQLite

        This returns a str which will then be executed in our SQLite db

        Here is the "jenkins" table layout:
         - date is the primary key, and it is the Unix timestamp as an int
         - nonpassing is the number of !(SUCCESS) jobs as an int
         - failing is the number of FAILURE jobs as an int
         - total is the total number of jobs on the Jenkins server as an int
        """

        command = "CREATE TABLE IF NOT EXISTS jenkins (date INTEGER PRIMARY "
        command += "KEY, nonpassing INTEGER, failing INTEGER, total INTEGER);"

        return command

    def sqlite_add(self):
        """Add data to the SQLite db

        This retrieves the current data from the Jenkins server, and returns a
        str which will then be executed in our SQLite db
        """

        # Match the variable names with the column names in the db
        nonpassing, failing, total = self._get_data()
        date = "strftime('%s', 'now')"

        # Craft the str
        command = "INSERT INTO jenkins VALUES ({}, {}, {}, {});".format(
                date, nonpassing, failing, total)

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

        command = "SELECT * FROM jenkins WHERE date > %s;" % unix_time

        return command

    def render_template(self, days, data):
        """Render a template with days in the filename, given the data

        The above function sqlite_time_range() is ran on the database with
        some predetermined date ranges. This function actually interprets that
        data, uses Jinja2 to magically render a template, and voila.
        """

        # Initialize a (softly) ephemeral dict to store data
        jenkins = {}
        _data = {"date": [], "nonpassing": [], "failing": [], "total": []}

        # Put the data from the DB query into _data
        for row in data:
            _data["date"].append(row[0])
            _data["nonpassing"].append(row[1])
            _data["failing"].append(row[2])
            _data["total"].append(row[3])

        # Get human-readable averages and throw it in a dict
        average = {}
        for datatype in ("nonpassing", "failing", "total"):
            try:
                num = sum(_data[datatype]) / len(_data[datatype])
                num = format(num, ".1f")
            except ZeroDivisionError:
                num = 0
            average[datatype] = num

        # Assign data to the dict Jinja2 is actually going to use
        jenkins = {"nonpassing": zip(_data["date"], _data["nonpassing"]),
                   "failing": zip(_data["date"], _data["failing"]),
                   "total": zip(_data["date"], _data["total"])}

        # Make the output dir if it doesn't already exist
        if not path.exists("output"):
            makedirs("output")

        src = path.join("templates", "jenkins.html")
        dest = path.join("output", "jenkins_%sdays.html" % days)
        jinja2_template(src, dest, jenkins=jenkins, average=average,
                days=days)

        # Return the averages for use in the summary
        return (average["nonpassing"], average["failing"], average["total"])
