#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
InfoEx <-> NRCS/MesoWest Auto Wx implementation
Alexander Vasarab
Wylark Mountaineering LLC

This program fetches data from either an NRCS SNOTEL site or MesoWest
weather station and pushes it to InfoEx using the new automated weather
system implementation.

It is designed to be run hourly, and it asks for the last three hours
of data of each desired type, and selects the most recent one. This
lends some resiliency to the process and helps ensure that we have a
value to send, but it can lead to somewhat inconsistent/untruthful
data if e.g. the HS is from the last hour but the tempPres is from two
hours ago because the instrumentation had a hiccup. It's worth
considering if this is a bug or a feature.

For more information, see file: README
For licensing, see file: LICENSE
"""

import configparser
import csv
import datetime
import logging
import os
import sys
import time
import urllib3
import importlib.util

from ftplib import FTP
from argparse import ArgumentParser

import pytz

import requests

import zeep
import zeep.cache
import zeep.transports

__version__ = '3.3.1'

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.NOTSET)

urllib3.disable_warnings()

def get_parser():
    """Return OptionParser for this program"""
    parser = ArgumentParser()

    parser.add_argument("--version",
                        action="version",
                        version=__version__)

    parser.add_argument("--config",
                        dest="config",
                        metavar="FILE",
                        help="location of config file")

    parser.add_argument("--log-level",
                        dest="log_level",
                        default=None,
                        help="set the log level (debug, info, warning)")

    parser.add_argument("--dry-run",
                        action="store_true",
                        dest="dry_run",
                        default=False,
                        help="fetch data but don't upload to InfoEx")

    return parser

def setup_config(config):
    """Setup config variable based on values specified in the ini file"""
    try:
        infoex = {
            'host': config['infoex']['host'],
            'uuid': config['infoex']['uuid'],
            'api_key': config['infoex']['api_key'],
            'csv_filename': config['infoex']['csv_filename'],
            'location_uuid': config['infoex']['location_uuid'],
            'wx_data': {}, # placeholder key, values to come later
        }

        station = dict()
        station['provider'] = config['station']['type']

        if station['provider'] not in ['nrcs', 'mesowest', 'python']:
            print("Please specify either nrcs or mesowest as the station type.")
            sys.exit(1)

        if station['provider'] == 'nrcs':
            station['source'] = 'https://wcc.sc.egov.usda.gov/awdbWebService/services?WSDL'
            station['station_id'] = config['station']['station_id']
            station['desired_data'] = config['station']['desired_data'].split(',')
            station['units'] = config['station']['units']

        if station['provider'] == 'mesowest':
            station['source'] = 'https://api.synopticdata.com/v2/stations/timeseries'
            station['station_id'] = config['station']['station_id']
            station['units'] = config['station']['units']
            station['desired_data'] = config['station']['desired_data']

            # construct full API URL (sans start/end time, added later)
            station['source'] = station['source'] + '?token=' + \
                                config['station']['token'] + \
                                '&within=60&units=' + station['units'] + \
                                '&stid=' + station['station_id'] + \
                                '&vars=' + station['desired_data']

        if station['provider'] == 'python':
            station['path'] = config['station']['path']

        tz = 'America/Los_Angeles'

        if 'tz' in config['station']:
            tz = config['station']['tz']

        try:
            station['tz'] = pytz.timezone(tz)
        except pytz.exceptions.UnknownTimeZoneError:
            LOG.critical("%s is not a valid timezone", tz)
            sys.exit(1)

        # By default, fetch three hours of data
        #
        # If user wants hn24 or wind averaging, then
        # we need more.
        station['num_hrs_to_fetch'] = 3

        # HN24
        if 'hn24' in config['station']:
            if config['station']['hn24'] not in ['true', 'false']:
                raise ValueError("hn24 must be either 'true' or 'false'")

            if config['station']['hn24'] == "true":
                station['hn24'] = True
                station['num_hrs_to_fetch'] = 24
            else:
                station['hn24'] = False
        else:
            # default to False
            station['hn24'] = False

        # Wind mode
        if 'wind_mode' in config['station']:
            if config['station']['wind_mode'] not in ['normal', 'average']:
                raise ValueError("wind_mode must be either 'normal' or 'average'")

            station['wind_mode'] = config['station']['wind_mode']

            if station['wind_mode'] == "average":
                station['num_hrs_to_fetch'] = 24
        else:
            # default to False
            station['wind_mode'] = "normal"

    except KeyError as err:
        LOG.critical("%s not defined in configuration file", err)
        sys.exit(1)
    except ValueError as err:
        LOG.critical("%s", err)
        sys.exit(1)

    # all sections/values present in config file, final sanity check
    try:
        for key in config.sections():
            for subkey in config[key]:
                if not config[key][subkey]:
                    raise ValueError
    except ValueError:
        LOG.critical("Config value '%s.%s' is empty", key, subkey)
        sys.exit(1)

    return (infoex, station)

def setup_logging(log_level):
    """Setup our logging infrastructure"""
    try:
        from systemd.journal import JournalHandler
        LOG.addHandler(JournalHandler())
    except ImportError:
        ## fallback to syslog
        #import logging.handlers
        #LOG.addHandler(logging.handlers.SysLogHandler())
        # fallback to stdout
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s.%(msecs)03d '
                                      '%(levelname)s %(module)s - '
                                      '%(funcName)s: %(message)s',
                                      '%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        LOG.addHandler(handler)

    # ugly, but passable
    if log_level in [None, 'debug', 'info', 'warning']:
        if log_level == 'debug':
            LOG.setLevel(logging.DEBUG)
        elif log_level == 'info':
            LOG.setLevel(logging.INFO)
        elif log_level == 'warning':
            LOG.setLevel(logging.WARNING)
        else:
            LOG.setLevel(logging.NOTSET)
    else:
        return False

    return True

def main():
    """Main routine: sort through args, decide what to do, then do it"""
    parser = get_parser()
    options = parser.parse_args()

    config = configparser.ConfigParser(allow_no_value=False)

    if not options.config:
        parser.print_help()
        print("\nPlease specify a configuration file via --config.")
        sys.exit(1)

    config.read(options.config)

    if not setup_logging(options.log_level):
        parser.print_help()
        print("\nPlease select an appropriate log level or remove the switch (--log-level).")
        sys.exit(1)

    (infoex, station) = setup_config(config)

    LOG.debug('Config parsed, starting up')

    # create mappings
    (fmap, final_data) = setup_infoex_fields_mapping(infoex['location_uuid'])
    iemap = setup_infoex_counterparts_mapping(station['provider'])

    # override units if user selected metric
    if station['provider'] != 'python' and station['units'] == 'metric':
        final_data = switch_units_to_metric(final_data, fmap)

    (begin_date, end_date) = setup_time_values(station)

    if station['provider'] == 'python':
        LOG.debug("Getting custom data from external Python program")
    else:
        LOG.debug("Getting %s data from %s to %s (%s)",
                  str(station['desired_data']),
                  str(begin_date), str(end_date), end_date.tzinfo.zone)

    time_all_elements = time.time()

    # get the data
    if station['provider'] == 'nrcs':
        infoex['wx_data'] = get_nrcs_data(begin_date, end_date, station)
    elif station['provider'] == 'mesowest':
        infoex['wx_data'] = get_mesowest_data(begin_date, end_date,
                                              station)
    elif station['provider'] == 'python':
        try:
            spec = importlib.util.spec_from_file_location('custom_wx',
                                                          station['path'])
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.LOG = LOG

            try:
                infoex['wx_data'] = mod.get_custom_data()

                if infoex['wx_data'] is None:
                    infoex['wx_data'] = []
            except Exception as exc:
                LOG.error("Python program for custom Wx data failed in "
                          "execution: %s", str(exc))
                sys.exit(1)

            LOG.info("Successfully executed external Python program")
        except ImportError:
            LOG.error("Please upgrade to Python 3.3 or later")
            sys.exit(1)
        except FileNotFoundError:
            LOG.error("Specified Python program for custom Wx data "
                      "was not found")
            sys.exit(1)
        except Exception as exc:
            LOG.error("A problem was encountered when attempting to "
                      "load your custom Wx program: %s", str(exc))
            sys.exit(1)

    LOG.info("Time taken to get all data : %.3f sec", time.time() -
             time_all_elements)

    LOG.debug("infoex[wx_data]: %s", str(infoex['wx_data']))

    # timezone massaging
    final_end_date = end_date.astimezone(station['tz'])

    # Now we only need to add in what we want to change thanks to that
    # abomination of a variable declaration earlier
    final_data[fmap['Location UUID']] = infoex['location_uuid']
    final_data[fmap['obDate']] = final_end_date.strftime('%m/%d/%Y')
    final_data[fmap['obTime']] = final_end_date.strftime('%H:%M')
    final_data[fmap['timeZone']] = station['tz'].zone

    for element_cd in infoex['wx_data']:
        if element_cd not in iemap:
            LOG.warning("BAD KEY wx_data['%s']", element_cd)
            continue

        if infoex['wx_data'][element_cd] is None:
            continue

        # do the conversion before the rounding
        if station['provider'] == 'nrcs' and station['units'] == 'metric':
            infoex['wx_data'][element_cd] = convert_nrcs_units_to_metric(element_cd, infoex['wx_data'][element_cd])

        # Massage precision of certain values to fit InfoEx's
        # expectations
        #
        # 0 decimal places: relative humidity, wind speed, wind
        #                   direction, wind gust, snow depth
        # 1 decimal place:  air temp, baro
        # Avoid transforming None values
        if element_cd in ['wind_speed', 'WSPD', 'wind_direction',
                          'RHUM', 'relative_humidity', 'WDIR',
                          'wind_gust', 'SNWD', 'snow_depth',
                          'hn24']:
            infoex['wx_data'][element_cd] = round(infoex['wx_data'][element_cd])
        elif element_cd in ['TOBS', 'air_temp', 'PRES', 'pressure']:
            infoex['wx_data'][element_cd] = round(infoex['wx_data'][element_cd], 1)
        elif element_cd in ['PREC', 'precip_accum']:
            infoex['wx_data'][element_cd] = round(infoex['wx_data'][element_cd], 2)

        # CONSIDER: Casting every value to Float() -- need to investigate if
        #           any possible elementCds we may want are any other data
        #           type than float.
        #
        #           Another possibility is to query the API with
        #           getStationElements and temporarily store the
        #           storedUnitCd. But that's pretty network-intensive and
        #           may not even be worth it if there's only e.g. one or two
        #           exceptions to any otherwise uniformly Float value set.
        final_data[fmap[iemap[element_cd]]] = infoex['wx_data'][element_cd]

    LOG.debug("final_data: %s", str(final_data))

    if infoex['wx_data']:
        if not write_local_csv(infoex['csv_filename'], final_data):
            LOG.warning('Could not write local CSV file: %s',
                        infoex['csv_filename'])
            return 1

        if not options.dry_run:
            upload_csv(infoex['csv_filename'], infoex)

    LOG.debug('DONE')
    return 0

# data structure operations
def setup_infoex_fields_mapping(location_uuid):
    """
    Create a mapping of InfoEx fields to the local data's indexing scheme.

    INFOEX FIELDS

    This won't earn style points in Python, but here we establish a couple
    of helpful mappings variables. The reason this is helpful is that the
    end result is simply an ordered set, the CSV file. But we still may
    want to manipulate the values arbitrarily before writing that file.

    Also note that the current Auto Wx InfoEx documentation shows these
    keys in a graphical table with the "index" beginning at 1, but here we
    sanely index beginning at 0.
    """
    # pylint: disable=too-many-statements,multiple-statements,bad-whitespace
    fmap = {}                           ; final_data     = [None] * 29
    fmap['Location UUID'] = 0           ; final_data[0]  = location_uuid
    fmap['obDate'] = 1                  ; final_data[1]  = None
    fmap['obTime'] = 2                  ; final_data[2]  = None
    fmap['timeZone'] = 3                ; final_data[3]  = 'Pacific'
    fmap['tempMaxHour'] = 4             ; final_data[4]  = None
    fmap['tempMaxHourUnit'] = 5         ; final_data[5]  = 'F'
    fmap['tempMinHour'] = 6             ; final_data[6]  = None
    fmap['tempMinHourUnit'] = 7         ; final_data[7]  = 'F'
    fmap['tempPres'] = 8                ; final_data[8]  = None
    fmap['tempPresUnit'] = 9            ; final_data[9]  = 'F'
    fmap['precipitationGauge'] = 10     ; final_data[10] = None
    fmap['precipitationGaugeUnit'] = 11 ; final_data[11] = 'in'
    fmap['windSpeedNum'] = 12           ; final_data[12] = None
    fmap['windSpeedUnit'] = 13          ; final_data[13] = 'mph'
    fmap['windDirectionNum'] = 14       ; final_data[14] = None
    fmap['hS'] = 15                     ; final_data[15] = None
    fmap['hsUnit'] = 16                 ; final_data[16] = 'in'
    fmap['baro'] = 17                   ; final_data[17] = None
    fmap['baroUnit'] = 18               ; final_data[18] = 'inHg'
    fmap['rH'] = 19                     ; final_data[19] = None
    fmap['windGustSpeedNum'] = 20       ; final_data[20] = None
    fmap['windGustSpeedNumUnit'] = 21   ; final_data[21] = 'mph'
    fmap['windGustDirNum'] = 22         ; final_data[22] = None
    fmap['dewPoint'] = 23               ; final_data[23] = None
    fmap['dewPointUnit'] = 24           ; final_data[24] = 'F'
    fmap['hn24Auto'] = 25               ; final_data[25] = None
    fmap['hn24AutoUnit'] = 26           ; final_data[26] = 'in'
    fmap['hstAuto'] = 27                ; final_data[27] = None
    fmap['hstAutoUnit'] = 28            ; final_data[28] = 'in'

    return (fmap, final_data)

def setup_infoex_counterparts_mapping(provider):
    """
    Create a mapping of the NRCS/MesoWest fields that this program supports to
    their InfoEx counterparts
    """
    iemap = {}

    if provider == 'nrcs':
        iemap['PREC'] = 'precipitationGauge'
        iemap['TOBS'] = 'tempPres'
        iemap['TMAX'] = 'tempMaxHour'
        iemap['TMIN'] = 'tempMinHour'
        iemap['SNWD'] = 'hS'
        iemap['PRES'] = 'baro'
        iemap['RHUM'] = 'rH'
        iemap['WSPD'] = 'windSpeedNum'
        iemap['WDIR'] = 'windDirectionNum'
        # unsupported by NRCS:
        # windGustSpeedNum
    elif provider == 'mesowest':
        iemap['precip_accum'] = 'precipitationGauge'
        iemap['air_temp'] = 'tempPres'
        iemap['air_temp_high_24_hour'] = 'tempMaxHour'
        iemap['air_temp_low_24_hour'] = 'tempMinHour'
        iemap['snow_depth'] = 'hS'
        iemap['pressure'] = 'baro'
        iemap['relative_humidity'] = 'rH'
        iemap['wind_speed'] = 'windSpeedNum'
        iemap['wind_direction'] = 'windDirectionNum'
        iemap['wind_gust'] = 'windGustSpeedNum'

        # NOTE: this doesn't exist in MesoWest, we create it in this
        #       program, so add it to the map here
        iemap['hn24'] = 'hn24Auto'
    elif provider == 'python':
        # we expect Python programs to use the InfoEx data type names
        iemap['precipitationGauge'] = 'precipitationGauge'
        iemap['tempPres'] = 'tempPres'
        iemap['tempMaxHour'] = 'tempMaxHour'
        iemap['tempMinHour'] = 'tempMinHour'
        iemap['hS'] = 'hS'
        iemap['baro'] = 'baro'
        iemap['rH'] = 'rH'
        iemap['windSpeedNum'] = 'windSpeedNum'
        iemap['windDirectionNum'] = 'windDirectionNum'
        iemap['windGustSpeedNum'] = 'windGustSpeedNum'

    return iemap


# provider-specific operations
def get_nrcs_data(begin, end, station):
    """get the data we're after from the NRCS WSDL"""
    transport = zeep.transports.Transport(cache=zeep.cache.SqliteCache())
    transport.session.verify = False
    client = zeep.Client(wsdl=station['source'], transport=transport)
    remote_data = {}

    # massage begin/end date format
    begin_date_str = begin.strftime('%Y-%m-%d %H:%M:00')
    end_date_str = end.strftime('%Y-%m-%d %H:%M:00')

    for element_cd in station['desired_data']:
        time_element = time.time()

        # get the last three hours of data for this elementCd/element_cd
        tmp = client.service.getHourlyData(
            stationTriplets=[station['station_id']],
            elementCd=element_cd,
            ordinal=1,
            beginDate=begin_date_str,
            endDate=end_date_str)

        LOG.info("Time to get NRCS elementCd '%s': %.3f sec", element_cd,
                 time.time() - time_element)

        values = tmp[0]['values']

        # sort and isolate the most recent
        #
        # NOTE: we do this because sometimes there are gaps in hourly data
        #       in NRCS; yes, we may end up with slightly inaccurate data,
        #       so perhaps this decision will be re-evaluated in the future
        if values:
            ordered = sorted(values, key=lambda t: t['dateTime'], reverse=True)
            remote_data[element_cd] = ordered[0]['value']
        else:
            remote_data[element_cd] = None

    return remote_data

def get_mesowest_data(begin, end, station):
    """get the data we're after from the MesoWest/Synoptic API"""
    remote_data = {}

    # massage begin/end date format
    begin_date_str = begin.strftime('%Y%m%d%H%M')
    end_date_str = end.strftime('%Y%m%d%H%M')

    # construct final, completed API URL
    api_req_url = station['source'] + '&start=' + begin_date_str + '&end=' + end_date_str

    try:
        req = requests.get(api_req_url)
    except requests.exceptions.ConnectionError:
        LOG.error("Could not connect to '%s'", api_req_url)
        sys.exit(1)

    try:
        json = req.json()
    except ValueError:
        LOG.error("Bad JSON in MesoWest response")
        sys.exit(1)

    try:
        observations = json['STATION'][0]['OBSERVATIONS']
    except KeyError as exc:
        LOG.error("Unexpected JSON in MesoWest response: '%s'", exc)
        sys.exit(1)
    except IndexError as exc:
        LOG.error("Unexpected JSON in MesoWest response: '%s'", exc)
        try:
            LOG.error("Detailed MesoWest response: '%s'",
                      json['SUMMARY']['RESPONSE_MESSAGE'])
        except KeyError:
            pass
        sys.exit(1)
    except ValueError as exc:
        LOG.error("Bad JSON in MesoWest response: '%s'", exc)
        sys.exit(1)

    # pos represents the last item in the array, aka the most recent
    pos = len(observations['date_time']) - 1

    # while these values only apply in certain cases, init them here
    wind_speed_values = []
    wind_gust_speed_values = []
    wind_direction_values = []
    hn24_values = []

    # results
    wind_speed_avg = None
    wind_gust_speed_avg = None
    wind_direction_avg = None
    hn24 = None

    for element_cd in station['desired_data'].split(','):
        # sort and isolate the most recent, see note above in NRCS for how and
        # why this is done
        #
        # NOTE: Unlike in the NRCS case, the MesoWest API response contains all
        #       data (whereas with NRCS, we have to make a separate request for
        #       each element we want). This is nice for network efficiency but
        #       it means we have to handle this part differently for each.
        #
        # NOTE: Also unlike NRCS, MesoWest provides more granular data; NRCS
        #       provides hourly data, but MesoWest can often provide data every
        #       10 minutes -- though this provides more opportunity for
        #       irregularities

        # we may not have the data at all
        key_name = element_cd + '_set_1'

        if key_name in observations:
            # val is what will make it into the dataset, after
            # conversions... it gets defined here because in certain
            # cases we need to look at all of the data to calculate HN24
            # or wind averages, but for the rest of the data, we only
            # take the most recent
            val = None

            # loop through all observations for this key_name
            # record relevant values for wind averaging or hn24, but
            # otherwise only persist the data if it's the last datum in
            # the set
            for idx, _ in enumerate(observations[key_name]):
                val = observations[key_name][idx]

                # skip bunk vals
                if val is None:
                    continue

                # mesowest by default provides wind_speed in m/s, but
                # we specify 'english' units in the request; either way,
                # we want mph
                if element_cd in ('wind_speed', 'wind_gust'):
                    val = kn_to_mph(val)

                # mesowest provides HS in mm, not cm; we want cm
                if element_cd == 'snow_depth' and station['units'] == 'metric':
                    val = mm_to_cm(val)

                # HN24 / wind_mode transformations, once the data has
                # completed unit conversions
                if station['wind_mode'] == "average":
                    if element_cd == 'wind_speed' and val is not None:
                        wind_speed_values.append(val)
                    elif element_cd == 'wind_gust' and val is not None:
                        wind_gust_speed_values.append(val)
                    elif element_cd == 'wind_direction' and val is not None:
                        wind_direction_values.append(val)

                if element_cd == 'snow_depth':
                    hn24_values.append(val)

                # again, only persist this datum to the final data if
                # it's from the most recent date
                if idx == pos:
                    remote_data[element_cd] = val

            # ensure that the data is filled out
            if not observations[key_name][pos]:
                remote_data[element_cd] = None
        else:
            remote_data[element_cd] = None

    if len(hn24_values) > 0:
        # instead of taking MAX - MIN, we want the first value (most
        # distant) - the last value (most recent)
        #
        # if the result is positive, then we have HN24; if it's not,
        # then we have settlement
        #hn24 = max(hn24_values) - min(hn24_values)
        hn24 = hn24_values[0] - hn24_values[len(hn24_values)-1]

        if hn24 < 0.0:
            # this case represents HS settlement
            #
            # TODO: determine if InfoEx supports auto-stations reporting
            #       HS settlement values
            hn24 = 0.0

    if len(wind_speed_values) > 0:
        wind_speed_avg = sum(wind_speed_values) / len(wind_speed_values) 

    if len(wind_gust_speed_values) > 0:
        wind_gust_speed_avg = sum(wind_gust_speed_values) / len(wind_gust_speed_values) 

    if len(wind_direction_values) > 0:
        wind_direction_avg = sum(wind_direction_values) / len(wind_direction_values) 

    if hn24 is not None:
        remote_data['hn24'] = hn24

    # overwrite the following with the respective averages, if
    # applicable
    if wind_speed_avg is not None:
        remote_data['wind_speed'] = wind_speed_avg

    if wind_gust_speed_avg is not None:
        remote_data['wind_gust'] = wind_gust_speed_avg

    if wind_direction_avg is not None:
        remote_data['wind_direction'] = wind_direction_avg

    return remote_data

def switch_units_to_metric(data_map, mapping):
    """replace units with metric counterparts"""

    # NOTE: to update this, use the fmap<->final_data mapping laid out
    #       in setup_infoex_fields_mapping ()
    data_map[mapping['tempMaxHourUnit']] = 'C'
    data_map[mapping['tempMinHourUnit']] = 'C'
    data_map[mapping['tempPresUnit']] = 'C'
    data_map[mapping['precipitationGaugeUnit']] = 'mm'
    data_map[mapping['hsUnit']] = 'cm'
    data_map[mapping['windSpeedUnit']] = 'm/s'
    data_map[mapping['windGustSpeedNumUnit']] = 'm/s'
    data_map[mapping['dewPointUnit']] = 'C'
    data_map[mapping['hn24AutoUnit']] = 'cm'
    data_map[mapping['hstAutoUnit']] = 'cm'

    return data_map

def convert_nrcs_units_to_metric(element_cd, value):
    """convert NRCS values from English to metric"""
    if element_cd == 'TOBS':
        value = f_to_c(value)
    elif element_cd == 'SNWD':
        value = in_to_cm(value)
    elif element_cd == 'PREC':
        value = in_to_mm(value)
    return value

# CSV operations
def write_local_csv(path_to_file, data):
    """Write the specified CSV file to disk"""
    with open(path_to_file, 'w') as file_object:
        # The requirement is that empty values are represented in the CSV
        # file as "", csv.QUOTE_NONNUMERIC achieves that
        LOG.debug("writing CSV file '%s'", path_to_file)
        writer = csv.writer(file_object, quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(data)
        file_object.close()
    return True

def upload_csv(path_to_file, infoex_data):
    """Upload the specified CSV file to InfoEx FTP and remove the file"""
    with open(path_to_file, 'rb') as file_object:
        LOG.debug("uploading FTP file '%s'", infoex_data['host'])
        ftp = FTP(infoex_data['host'], infoex_data['uuid'],
                  infoex_data['api_key'])
        ftp.storlines('STOR ' + path_to_file, file_object)
        ftp.close()
        file_object.close()
    os.remove(path_to_file)

# other miscellaneous routines
def setup_time_values(station):
    """establish time bounds of data request(s)"""

    # default timezone to UTC (for MesoWest)
    tz = pytz.utc

    # but for NRCS, use the config-specified timezone
    if station['provider'] == 'nrcs':
        tz = station['tz']

    # floor time to nearest hour
    date_time = datetime.datetime.now(tz=tz)
    end_date = date_time - datetime.timedelta(minutes=date_time.minute % 60,
                                              seconds=date_time.second,
                                              microseconds=date_time.microsecond)
    begin_date = end_date - datetime.timedelta(hours=station['num_hrs_to_fetch'])
    return (begin_date, end_date)

def f_to_c(f):
    """convert Fahrenheit to Celsius"""
    return (float(f) - 32) * 5.0/9.0

def in_to_cm(inches):
    """convert inches to centimetrs"""
    return float(inches) * 2.54

def in_to_mm(inches):
    """convert inches to millimeters"""
    return (float(inches) * 2.54) * 10.0

def ms_to_mph(ms):
    """convert meters per second to miles per hour"""
    return ms * 2.236936

def kn_to_mph(kn):
    """convert knots to miles per hour"""
    return kn * 1.150779

def mm_to_cm(mm):
    """convert millimeters to centimetrs"""
    return mm / 10.0

if __name__ == "__main__":
    sys.exit(main())
