InfoEx AutoWx (IEAW)
=============

This program fetches data from an NRCS SNOTEL or MesoWest station, or
your own custom data source, and pushes it into the InfoEx system using
the new automated weather system implementation.

Licensed under the ISC license (see file: LICENSE).

Disclaimer
----------

Your usage of the NRCS, MesoWest, and/or InfoEx systems is bound by
their respective terms and this software makes no attempt or claim to
abide by any such terms.

Installation
------------

It's recommended to use venv and pip with this program. Here's a typical
sequence of commands for a new setup:

`$ cd /path/to/src`  
`$ python3 -m venv env`  
`$ . env/bin/activate`  
`$ pip install -r requirements.txt`  

How to use it
-------------

This program is designed to be run from the command line (or via
cron(8)) and administered via a simple, concise configuration file.

This design allows you to run a separate program instance for each NRCS
or MesoWest weather station from which you'd like to automate the
importation of data into your InfoEx subscriber account.

To get started, copy the included example config file
(`config.ini.example` in the root source directoy) and modify the values
for your own use.

To run ad-hoc (be sure to activate the virtual environment, as detailed in the
Installation section):

`./infoex-autowx.py --config path/to/config-file.ini [--dry-run] [--log-level debug|info|warning]`

**NOTE: Specifying --dry-run will not clean up the generated CSV file.**
This is so that you can more easily debug any issues that arise in the
setup process.

You can also specify `--log-level` as debug, info, warning. The
log messages produced by the program will try to be logged to journald,
but if that's not available, they will be printed to stdout. This output
can be helpful early on in the setup process.

Automation
----------

Here's an example of a crontab(5) with two SNOTEL sites, each of which
will run once per hour (note that this will activate the virtual environment
created earlier):

`2 * * * * /usr/bin/env bash -c 'cd /home/user/infoex-autowx && source env/bin/activate && ./infoex-autowx.py --config laurance-lake.ini'`  
`4 * * * * /usr/bin/env bash -c 'cd /home/user/infoex-autowx && source env/bin/activate && ./infoex-autowx.py --config mud-ridge.ini'`

Configuration File
------------------

The configuration file is separated into two parts, the [station]
portion, and the [infoex] portion.

The [station] values describe which weather station's data you're after.
See the next section in this README for instructions on obtaining these
values.

The [infoex] values describe your credentials for the InfoEx automated
weather station FTP server and other InfoEx-related configuration
options.

`[station]`  
`type = # mesowest, nrcs, or python #`  
`token = # MesoWest API token -- only applies when type is mesowest #`  
`station_id = # the NRCS/MesoWest identifier for a particular station #`  
`desired_data = # a comma-delimited list of fields you're interested in #`  
`units = # either english or metric -- only applies when type is mesowest #`  
`tz = # any entry from the Olson tz database e.g. America/Denver #`  
`path = # the filesystem path to the Python program -- only applies when type is python #`  
`wind_mode = # normal or average #`  
`hn24 = # yes or no #`  

`[infoex]`  
`host = # InfoEx FTP host address #`  
`uuid = # InfoEx-supplied UUID #`  
`api_key = # InfoEx-supplied API Key #`  
`csv_filename = # arbitrary name of the file that will be uploaded to InfoEx #`  
`location_uuid = # the UUID used by InfoEx to identify your automated Wx site #`  

Finding your NRCS `station` values
----------------------------------

To complete the [station] configuration section for an NRCS station, you
must fill in the attributes of the NRCS SNOTEL site from which you want
to import data.

Here are the steps to do that:

1. Find your station by clicking through this website:

   https://www.wcc.nrcs.usda.gov/snow/sntllist.html

   Or by using the interactive map:

   https://www.nrcs.usda.gov/wps/portal/wcc/home/quicklinks/imap

2. Once you've found your station, look for the "Station ID" (a 3- or
   4-digit number).

3. Combine your Station ID, state abbreviation, and the network type
   "SNTL" to get your NRCS station triplet (`station_id`, in the
   configuration file). For example:

   655:OR:SNTL

   would represent the Mud Ridge station (Station ID 655) in the state
   of Oregon (OR). SNTL just represents that the station is in the
   SNOTEL network and is used internally by NRCS.

Once you have your station ID, fill in the field in your configuration
file. Now you must select which data you'd like to pull from NRCS to
push into InfoEx.

For that, visit the NRCS web service:

https://wcc.sc.egov.usda.gov/awdbWebService/webservice/testwebservice.jsf?webserviceName=/awdbWebService

Click "getElements" on the left, and then click, "Test Operation." This
will return a long list of elements to your web browser from which you
can choose. Each returned element has its identifier and a description.

Once you've chosen your elements, combine all of their respective
"elementCd" values into a comma-delimited string and put that into your
configuration file as the `desired_data` value.

A complete [station] section example:

`[station]`  
`type = nrcs`  
`station_id = 655:OR:SNTL`  
`desired_data = TOBS,PREC`

indicates that I'd like to import "AIR TEMPERATURE OBSERVED" and
"PRECIPITATION ACCUMULATION" from the NRCS SNOTEL site at Mud Ridge, OR,
into InfoEx.

Finding your MesoWest `station` values
--------------------------------------

MesoWest has great documentation which can be found here:

https://developers.synopticdata.com/mesonet/v2/getting-started/

To complete the [station] configuration section for a MesoWest station,
you must fill in the attributes of the MesoWest station ID from which
you want to import data. Here are the steps to do that:

1. Firstly, get set up with MesoWest's API by going to the above
   'Getting Started' link. Once you're set up, you can copy a token from
   the MesoWest web portal into your configuration file's `token` value.

2. Next, you will want to find the Station ID for the MesoWest weather
   station of interest and copy it to the `station_id` value.

3. Finally, you must choose what data types you want to push into
   InfoEx and compile them into a comma-separated list. MesoWest refers
   to these as 'field names' or 'station variables' and a list is
   available here:

https://developers.synopticdata.com/about/station-variables/

The MesoWest API supports on-the-fly unit conversion. If desired, that
can be specified to infoex-autowx via the configuration option `units`.
This can be either 'english' or 'metric', with 'english' meaning
imperial units as used in the United States.

A complete [station] section example:

`[station]`  
`type = mesowest`  
`token = # token id copied from MesoWest web account #`  
`station_id = OD110`  
`desired_data = air_temp,snow_depth`  
`units = english`

indicates that I'd like to import "Temperature" and "Precipitation
accumulated" from the MesoWest station at Santiam Pass, OR, into InfoEx,
and that I want that data in imperial units.

Three- versus 24-hour ranges
----------------------------

By default, this program will fetch three hours of data from the
provider. This way, if the most recent record has any missing data, it
can examine the two hours prior, using whatever data it can find.

There are two features which will cause the program to expand the time
range of fetched data from three to 24 hours. Please be aware of this
expansion as it may cause a rise in data/API usage.

**NOTE: Only MesoWest stations have the benefit of wind averaging and
        HN24 calculation at this time, because generally NRCS SNOTEL
		stations do not provide wind data. HN24 support for NRCS SNOTEL
		is planned.

### Wind mode
If you go to submit a Wx observation in InfoEx at e.g. 05:05, and have
so configured InfoEx, it will take the wind speed, wind gust speed, and
wind direction, from that hour and auto-fill it for the observation.

Some operations may find it more important to know the averages for
those values over the prior 24 hour period. Setting `wind_mode` to
`average` will enable that.

### HN24
As most stations do not provide HN24 on their own, this program provides
a configuration option for calculating this. Simply add `hn24 = true` to
the configuration file.

*NOTE: This is its own configuration option, rather than a new value for
	   desired_data, because it's not technically provided by MesoWest
	   or NRCS SNOTEL.*

Custom weather station support
------------------------------

This program supports custom weather station data by allowing the user
to specify the path to an external Python program. The external Python
program should emit its data in the form expected by infoex-autowx.

This is a powerful feature which enables the user to upload data from
any source imaginable into InfoEx. Common examples are a local database
or a remote web page which requires some custom parsing.

Please see the program located at examples/custom-wx.example.py for a
complete description of what's required.

A note on time zones
--------------------

This program is aware of time zones via the pytz library. The way in
which NRCS and MesoWest deal with time zones differs as follows:

NRCS expects the request to come in the appropriate time zone, and the
data retrieved will be in the same time zone (no transformation
required before sending to InfoEx).

MesoWest expects the request to come in UTC, and the data retrieved will
be in the same time zone (transformation from UTC to the desired time
zone is required before sending to InfoEx).

As long as you specify the correct timezone in your configuration file,
all will be handled correctly. The list of time zones comes from the
Olson tz database. See that for more information.

If you specify an invalid time zone, the program will exit and inform
you of such.

Lastly, InfoEx itself is timezone aware. If you notice that the data
which makes it into your operation is inaccurate, start your
investigation with time zone-related issues and move on only once you've
ruled this out as a cause of the inaccuracy.

Unit conversions
----------------

Desired units may be specified in the configuration file.

For MesoWest, the desired unit will be passed along in the API request
and the conversion will take place through the MesoWest/Synoptic API.

For NRCS, this program will do the conversion manually, as NRCS does not
permit specifying the desired unit.

A note on supported measurements
--------------------------------

While this program supports several measurements, and will faithfully
request all of the ones you specify (provided they're supported), the
weather station may not record them. In this case, the data will simply
be ignored (i.e. it will NOT log "0" when there's no measurement
available).

InfoEx provides a mechanism for inspecting your automated weather
station data, so use that after setting this program up and compare it
with the data you see in your web browser.

Here's the list of measurements currently supported:

**NRCS:**  
PREC  
TOBS  
SNWD  
PRES  
RHUM  
WSPD  
WDIR  

**MesoWest:**  
precip\_accum  
air\_temp  
snow\_depth  
pressure  
relative\_humidity  
wind\_speed  
wind\_direction  
wind\_gust  

**Custom Wx program**  
*infoex-autowx expects a custom Wx data provider to provide at least one
of the following:*  
precipitationGauge  
tempPres  
tempMaxHour  
tempMinHour  
hS  
baro  
rH  
windSpeedNum  
windDirectionNum  
windGustSpeedNum  

Version history
---------------

- 3.3.1 (Jan 2022)

  Fix bug in which HN24 values under certain circumstances could be
  inaccurate.

- 3.3.0 (Nov 2021)

  Implement wind averaging and auto-calculation of HN24. These are
  opt-in via two new configuration options.

- 3.2.4 (Mar 2021)

  Fix a small bug that allowed MesoWest HS values to flow through in
  millimeters when metric was the specified unit. MesoWest metric HS
  values are now correctly in centimeters.

- 3.2.3 (Feb 2021)

  Fix a small bug that allowed a TypeError to be raised with some
  regularity.

- 3.2.2 (Feb 2021)

  Various small fixes.

  - Round precipitation accumulation values to 2 decimal places.
  - Catch requests' ConnectionException.
  - Improve logging output when using stdout.

- 3.2.1 (Feb 2021)

  Fix config validation bug with units and custom Python program.

- 3.2.0 (Feb 2021)

  Implement NRCS unit conversion.

- 3.1.1 (Feb 2021)

  Fix relative humidity rounding.

- 3.1.0 (Jan 2021)

  Implement time zone support.

- 3.0.2 (Jan 2021)

  Use UTC time when asking MesoWest for data.

- 3.0.1 (Jan 2021)

  General fixes.

  - MesoWest wind data (speed and gust speed) units are now transformed
    from their origin unit (meters per second) to the unit expected by
    InfoEx (miles per hour).

  - Relative humidity is now rounded to one decimal place, preventing
    InfoEx from reddening the auto-filled value.

- 3.0.0 (Nov 2020)

  Implement Custom Wx data providers.

  This release enables the user to write their own Python programs and
  specify them to infoex-autowx as a data provider.

  This in turn enables the user to pull data from e.g. a local database
  or an HTML page and push it into their InfoEx auto station data,
  limited only by the imagination.

- 2.2.0 (Nov 2020)

  Add support for Tmin/Tmax values (directly from MesoWest/NRCS).

- 2.1.0 (Nov 2020)

  Adjust precision of certain values before sending them to InfoEx.

- 2.0.2 (Jul 2020)

  Fix issues shown by pylint(1).

- 2.0.1 (Jul 2020)

  Major restructuring, but nothing which should impact the end user.

  - Took the monolithic main () routine and broke it out into logical
    components.
  - Improved the names of variables.

- 2.0.0 (Jul 2020)

  Implement MesoWest integration.

  This release also makes significant changes to the configuration file,
  hence the major version bump. Such changes are not taken lightly but
  given the desire to support multiple data sources, were necessary.

  Other minor changes include:

  - New switches: --log-level and --version.
  - Better documentation.
  - Expanded supported measurement types (from three to eight, in number).

- 1.0.0 (Jun 2020)

  First released version. Cleaned up the program and design.
  Implemented configuration file, added LICENSE, README, docs, etc.

- 0.8.0 (Apr 2020)

  First finished (unreleased) version.

- pre-0.8.0 (Apr 2020)

  First (private) finished implementation with successful importation of
  NRCS data into InfoEx.
