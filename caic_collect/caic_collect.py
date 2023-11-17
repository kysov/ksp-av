import requests
import re
import csv
import html
import os
from datetime import datetime

# Function to clean HTML content
def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return html.unescape(cleantext)

# Mapping for danger ratings
danger_rating_map = {
    'low': 1,
    'moderate': 2,
    'considerable': 3,
    'high': 4,
    'extreme': 5,
    'noRating': 0,
    'noForecast': 0
}

# Function to convert danger ratings
def convert_danger_ratings(danger_ratings):
    # Initialize the list with zeros for all expected positions
    converted_ratings = [0] * 9
    for idx, rating in enumerate(danger_ratings):
        # Map the string ratings to their numeric values
        converted_ratings[idx*3] = danger_rating_map.get(rating['alp'].lower(), 0)
        converted_ratings[idx*3 + 1] = danger_rating_map.get(rating['tln'].lower(), 0)
        converted_ratings[idx*3 + 2] = danger_rating_map.get(rating['btl'].lower(), 0)
    return converted_ratings

# Function to fetch data from the API
def fetch_data(api_endpoint):
    try:
        response = requests.get(api_endpoint)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

# Function to write CSV content to a given file object
def write_csv_content(data, file, append=False):
    fieldnames = [
        'Forecaster', 'IssueDateTime', 'Title', 'AvalancheSummary',
        'Message', 'ConfidenceRating', 'TodayDangerRatingAlp',
        'TodayDangerRatingTln', 'TodayDangerRatingBtl',
        'TomorrowDangerRatingAlp', 'TomorrowDangerRatingTln',
        'TomorrowDangerRatingBtl', 'DayAfterTomorrowDangerRatingAlp',
        'DayAfterTomorrowDangerRatingTln', 'DayAfterTomorrowDangerRatingBtl'
    ]
    writer = csv.DictWriter(file, fieldnames=fieldnames)

    # Only write headers if not appending
    if not append:
        writer.writeheader()

    for forecast in data:
        # Default values for fields
        confidence_rating = 'noRating'
        danger_ratings = [0] * 9

        # Check and assign the confidence rating if available
        if 'confidence' in forecast and 'days' in forecast['confidence'] and forecast['confidence']['days']:
            confidence_rating = forecast['confidence']['days'][0].get('rating', 'noRating').lower()

        # Check and convert danger ratings if available and type is 'avalancheforecast'
        if forecast['type'] == 'avalancheforecast' and 'dangerRatings' in forecast and 'days' in forecast['dangerRatings']:
            danger_ratings = convert_danger_ratings(forecast['dangerRatings']['days'])

        # Skip entries with 'No Forecast' danger ratings
        if forecast['type'] == 'avalancheforecast' and all(danger_rating == 0 for danger_rating in danger_ratings):
            continue

        # Extract the relevant fields
        title = forecast.get('title', 'No title')
        forecaster = forecast.get('forecaster', 'No forecaster')
        issue_datetime = forecast.get('issueDateTime', 'No issue date time')

        # Process both 'avalancheforecast' and 'regionaldiscussion'
        avalanche_summary = ''
        message = ''
        if forecast.get('avalancheSummary', {}).get('days'):
            first_day_summary = forecast['avalancheSummary']['days'][0]
            if first_day_summary:
                avalanche_summary = clean_html(first_day_summary.get('content', ''))
        elif forecast['type'] == 'regionaldiscussion':
            message = clean_html(forecast.get('message', ''))

        numeric_confidence_rating = danger_rating_map.get(confidence_rating, 0)

        # Convert danger ratings, if available
        danger_ratings = convert_danger_ratings(forecast['dangerRatings']['days']) if 'dangerRatings' in forecast else [0] * 9

        # Create the CSV row
        csv_row = {
            'Forecaster': forecaster,
            'IssueDateTime': issue_datetime,
            'Title': title,
            'AvalancheSummary': avalanche_summary,
            'Message': message,
            'ConfidenceRating': numeric_confidence_rating,
            'TodayDangerRatingAlp': danger_ratings[0],
            'TodayDangerRatingTln': danger_ratings[1],
            'TodayDangerRatingBtl': danger_ratings[2],
            'TomorrowDangerRatingAlp': danger_ratings[3],
            'TomorrowDangerRatingTln': danger_ratings[4],
            'TomorrowDangerRatingBtl': danger_ratings[5],
            'DayAfterTomorrowDangerRatingAlp': danger_ratings[6],
            'DayAfterTomorrowDangerRatingTln': danger_ratings[7],
            'DayAfterTomorrowDangerRatingBtl': danger_ratings[8]
        }

        writer.writerow(csv_row)

# Function to write or append data to CSV files
def write_to_csv(data, daily_filename, master_filename):
    # Write to the daily CSV file (overwriting if it already exists)
    with open(daily_filename, mode='w', newline='', encoding='utf-8') as daily_file:
        write_csv_content(data, daily_file, append=False)
    
    # Check if the master file exists to determine if headers are needed
    headers_required = not os.path.isfile(master_filename)
    # Append to the master CSV file
    with open(master_filename, mode='a', newline='', encoding='utf-8') as master_file:
        write_csv_content(data, master_file, append=not headers_required)

            
# Main script logic
if __name__ == "__main__":
    # API endpoint configuration
    current_date = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    api_endpoint = f"https://avalanche.state.co.us/api-proxy/avid?_api_proxy_uri=/products/all?datetime={current_date}&includeExpired=true"
    
    # Fetch data from API
    forecasts_data = fetch_data(api_endpoint)
    
    # Check if data was successfully fetched
    if forecasts_data:
        # Define CSV filenames
        current_date_str = datetime.utcnow().strftime('%Y-%m-%d')
        csv_directory = '/workspaces/ksp-av/caic_collect/data'
        daily_csv_filename = f'{csv_directory}/avalanche_forecasts_{current_date_str}.csv'
        master_csv_filename = f'{csv_directory}/master_avalanche_forecasts.csv'
        
        # Ensure directory exists
        if not os.path.exists(csv_directory):
            os.makedirs(csv_directory)
        
        # Write data to the daily and master CSV files
        write_to_csv(forecasts_data, daily_csv_filename, master_csv_filename)
        print(f"Daily data has been written to: {daily_csv_filename}")
        print(f"Data has been appended to: {master_csv_filename}")
    else:
        print("Failed to fetch data from the API.")
