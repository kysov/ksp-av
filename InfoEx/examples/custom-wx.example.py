# reference implementation for an infoex-autowx custom Wx data provider

# global variable which will hold the Wx data to be uploaded to InfoEx
wx_data = {}

# the following data types are supported by infoex-autowx
wx_data['precipitationGauge'] = None
wx_data['tempPres'] = None
wx_data['tempMaxHour'] = None
wx_data['tempMinHour'] = None
wx_data['hS'] = None
wx_data['baro'] = None
wx_data['rH'] = None
wx_data['windSpeedNum'] = None
wx_data['windDirectionNum'] = None
wx_data['windGustSpeedNum'] = None

def get_custom_data():
    # This function will be called by infoex-autowx, and the `wx_data`
    # variable (a global variable within this program) will be returned.
    #
    # For example, maybe you will `import psycopg2` and grab your data
    # from a local PostgreSQL database. Or maybe you will use the
    # requests library to fetch a remote web page and parse out the data
    # that's meaningful to your operation.
    #
    # Whatever your program needs to do to get its data can be done
    # either here in this function directly, or elsewhere with
    # modification to the global variable `wx_data`.
    #
    # NOTE: The LOG class from infoex-autowx is available, so you may
    #       issue e.g. LOG.info('some helpful information') in your
    #       program.

    return wx_data
