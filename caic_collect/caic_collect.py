import requests
import html
import re
import csv
from datetime import datetime

# Function to clean HTML content
def clean_html(raw_html):
    cleanr = re.compile('<.*?>')  # Regex to find HTML tags
    cleantext = re.sub(cleanr, '', raw_html)  # Remove HTML tags
    return html.unescape(cleantext)  # Unescape HTML entities like &amp;, &lt;, etc.

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
    converted_ratings = []
    for rating in danger_ratings:
        # Assuming the data structure is {'days': [{'position': 1, 'alp': 'low', ...}, ...]}
        converted_ratings.extend([
            danger_rating_map.get(rating.get('alp', 'noRating'), 0),
            danger_rating_map.get(rating.get('tln', 'noRating'), 0),
            danger_rating_map.get(rating.get('btl', 'noRating'), 0)
        ])
    return converted_ratings

# API endpoint
api_endpoint = "https://avalanche.state.co.us/api-proxy/avid?_api_proxy_uri=/products/all?datetime={date}&includeExpired=true"
current_date = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
full_endpoint = api_endpoint.format(date=current_date)

# CSV setup
current_date_str = datetime.utcnow().strftime('%Y-%m-%d')
csv_filename = f'/workspaces/ksp-av/caic_collect/data/avalanche_forecasts_{current_date_str}.csv'

# Make the GET request
response = requests.get(full_endpoint)

# If the request was successful
if response.status_code == 200:
    # Parse the JSON response
    data = response.json()

    # Open the CSV file
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Write the headers
        writer.writerow([
            'Forecaster', 'IssueDateTime', 'Title', 'AvalancheSummary',
            'Message', 'ConfidenceRating', 'DangerRatingPosition1Alp',
            'DangerRatingPosition1Tln', 'DangerRatingPosition1Btl',
            'DangerRatingPosition2Alp', 'DangerRatingPosition2Tln',
            'DangerRatingPosition2Btl', 'DangerRatingPosition3Alp',
            'DangerRatingPosition3Tln', 'DangerRatingPosition3Btl'
        ])

        # Process each forecast
        for forecast in data:
            # Check if 'Title' contains 'Regional' and extract 'message' or 'avalancheSummary'
            if 'Regional' in forecast.get('title', ''):
                message = clean_html(forecast.get('message', 'No message'))
                avalanche_summary = ''
            else:
                message = ''
                days = forecast.get('avalancheSummary', {}).get('days', [])
                if days:  # Check if the list is not empty
                    avalanche_summary = clean_html(days[0].get('content', 'No summary'))
                else:
                    avalanche_summary = 'No summary'

            # Extract other required information
            forecaster = forecast.get('forecaster', 'No forecaster')
            issue_datetime = forecast.get('issueDateTime', 'No issue date time')
            title = forecast.get('title', 'No title')
            confidence_rating = forecast.get('confidence', {}).get('days', [{}])[0].get('rating', 'No rating')
            
            # Convert danger ratings
            danger_ratings = convert_danger_ratings(forecast.get('dangerRatings', {}).get('days', []))

            # Create the CSV row
            csv_row = [
                forecaster, issue_datetime, title, avalanche_summary,
                message, confidence_rating, *danger_ratings
            ]

            # Write the CSV row
            writer.writerow(csv_row)

    print(f"Data has been written to: {csv_filename}")

else:
    print(f"Failed to fetch data: {response.status_code}")
