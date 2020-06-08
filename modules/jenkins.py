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

from jenkinsapi.custom_exceptions import NoBuildData
from jenkinsapi.jenkins import Jenkins
from os import getenv

class JenkinsModule:
    """Jenkins module for the Metrics program"""

    def _auth_jenkins_server(self):
        """Authenticate to the Jenkins server

        This uses the API_SITE, API_USER, and API_KEY env vars.
        """
        # Load the API values from the environment variables
        api_site = getenv("API_SITE")
        api_user = getenv("API_USER")
        api_key = getenv("API_KEY")
        for envvar in [api_site, api_user, api_key]:
            if not envvar:
                raise ValueError("API_SITE, API_USER, and API_KEY must be",
                                 "defined")
        # Authenticate to the server
        server = Jenkins(api_site, username=api_user, password=api_key)

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
                status = val.get_last_build().get_status()
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
