import json
import requests

# Load the JSON data from the file
with open('sample_data.json', 'r') as f:
    data = json.load(f)

# Send the POST request to the API endpoint
response = requests.post('http://localhost:3000/send-emails', json=data)

# Display the response
print("Status code:", response.status_code)
print("Response:", response.json())
