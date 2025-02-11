import requests
import os
import urllib.parse
import json
import pandas as pd
from datetime import datetime
from flask import Flask, redirect, request, jsonify, session

# Set the working directory to the location of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Current working directory: {os.getcwd()}")

# Initialize the Flask application
app = Flask(__name__)
app.secret_key = 'Babou'  # Secret key for session management
CLIENT_ID = '8863c8c092a34323b81b2ed91a10c5ca'  # Spotify client ID
CLIENT_SECRET = 'da4a66d60516460c95dcc91f38800b3a'  # Spotify client secret
REDIRECT_URI = 'http://localhost:5000/callback'  # Redirect URI for Spotify authorization
AUTH_URL = 'https://accounts.spotify.com/authorize'  # URL for Spotify authorization
TOKEN_URL = 'https://accounts.spotify.com/api/token'  # URL to get the access token
API_BASE_URL = 'https://api.spotify.com/v1/'  # Spotify API base URL

def get_access_token():
    """
    Retrieves an access token from the session, refreshing it if expired.
    
    Returns:
        str: The access token for Spotify API.
    """
    # Check if the access token is expired or not present
    if 'access_token' not in session or datetime.now().timestamp() > session['expires_at']:
        if 'refresh_token' not in session:
            print('No refresh token found in session.')
            return None  # Return None if no refresh token is available
        # Prepare request body for refreshing the access token
        req_body = {
            'grant_type': 'refresh_token',
            'refresh_token': session['refresh_token'],
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }
        # Request a new access token using the refresh token
        response = requests.post(TOKEN_URL, data=req_body)
        if response.status_code != 200:
            print(f"Failed to refresh token: {response.text}")
            return None
        new_token_info = response.json()  # Get the response in JSON format
        # Store the new access token and its expiration time
        session['access_token'] = new_token_info['access_token']
        session['expires_at'] = datetime.now().timestamp() + new_token_info['expires_in']
    return session['access_token']  # Return the current valid access token

@app.route('/')
def index():
    """
    The index route renders the login screen with a link to log in with Spotify.
    
    Returns:
        str: The HTML for the login screen with a link to authenticate.
    """
    return "Login Screen <a href='/login'>Login With Spotify</a>"

@app.route('/login')
def login():
    """
    Initiates the Spotify login process, redirecting the user to Spotify's login page.
    
    Returns:
        Response: A redirect to Spotify's login URL.
    """
    # Define the required scope for the app (read private data and playlists)
    scope = 'user-read-private user-read-email playlist-read-private'
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': scope,
        'redirect_uri': REDIRECT_URI,
        'show_dialog': True
    }
    # Build the authorization URL and redirect the user
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """
    Handles the callback from Spotify after the user has authenticated.
    
    Returns:
        Response: Redirects the user to their playlists page or shows an error.
    """
    # Check if there is an error in the callback
    if 'error' in request.args:
        print(f"Callback error: {request.args['error']}")
        return jsonify({"error": request.args['error']})
    
    # Handle the authorization code exchange
    if 'code' in request.args:
        req_body = {
            'code': request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }
        response = requests.post(TOKEN_URL, data=req_body)
        if response.status_code != 200:
            print(f"Failed to get token: {response.text}")
            return jsonify({"error": "Failed to get token"})
        
        # Store the access and refresh tokens in the session
        token_info = response.json()
        session['access_token'] = token_info['access_token']
        session['refresh_token'] = token_info['refresh_token']
        session['expires_at'] = datetime.now().timestamp() + token_info['expires_in']
        return redirect('/playlists')

@app.route('/playlists')
def get_playlists():
    """
    Fetches the user's playlists from Spotify and redirects to the track listing.
    
    Returns:
        Response: A redirect to the /tracks endpoint with the playlist IDs.
    """
    # Get the access token to authenticate the API request
    access_token = get_access_token()
    if not access_token:
        print('No access token available, redirecting to login.')
        return redirect('/login')
    
    # Define headers for the request to Spotify API
    headers = {
        'Authorization': f"Bearer {access_token}"
    }
    
    # Request the user's playlists from Spotify API
    response = requests.get(API_BASE_URL + 'me/playlists', headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch playlists: {response.text}")
        return jsonify({"error": "Failed to fetch playlists"}), response.status_code
    
    # Extract playlist IDs from the response
    playlists = response.json()
    playlist_ids = [playlist['id'] for playlist in playlists['items']]
    print(f"Fetched playlists: {playlist_ids}")
    
    # Redirect to the /tracks endpoint with the playlist IDs as query parameters
    return redirect(f'/tracks?playlist_ids={"&playlist_ids=".join(playlist_ids)}')

@app.route('/tracks')
def get_tracks():
    """
    Retrieves track data from Spotify based on playlist IDs passed in the URL.
    
    Returns:
        JSON: The track data in JSON format.
    """
    # Extract playlist IDs from the query parameters
    playlist_ids = request.args.getlist('playlist_ids')
    # Fetch and save tracks for the specified playlists
    df = fetch_and_save_tracks(playlist_ids)
    return df.to_json(orient='records')

def fetch_and_save_tracks(playlist_ids):
    """
    Fetches track data for the given playlist IDs, saves it to JSON and CSV files, 
    and returns a pandas DataFrame.
    
    Args:
        playlist_ids (list): List of Spotify playlist IDs to fetch track data for.
    
    Returns:
        pd.DataFrame: A DataFrame containing the track data.
    """
    # Get the access token to authenticate the requests
    access_token = get_access_token()
    if not access_token:
        print('No access token available, redirecting to login.')
        return redirect('/login')
    
    # Define headers for the request
    headers = {
        'Authorization': f"Bearer {access_token}"
    }
    
    # Initialize lists to store the track data
    playlist_data = []
    track_data_list = []

    # Loop through each playlist ID
    for playlist_id in playlist_ids:
        # Fetch playlist details (name and other info)
        playlist_response = requests.get(API_BASE_URL + f'playlists/{playlist_id}', headers=headers)
        if playlist_response.status_code != 200:
            print(f"Failed to fetch playlist details for {playlist_id}: {playlist_response.text}")
            continue  # Skip this playlist if details can't be fetched
        
        # Extract the playlist name
        playlist_info = playlist_response.json()
        playlist_name = playlist_info['name']

        # Fetch the tracks in the playlist
        response = requests.get(API_BASE_URL + f'playlists/{playlist_id}/tracks', headers=headers)
        if response.status_code == 200:
            track_data = response.json()
            track_data_list.append(track_data)  # Store raw track data
            # Process each track in the playlist
            for item in track_data['items']:
                track_info = item['track']
                track_data = {
                    'playlist_id': playlist_id,  # Playlist ID
                    'playlist_name': playlist_name,  # Playlist name
                    'artist': track_info['artists'][0]['name'],  # Artist name
                    'track_name': track_info['name'],  # Track name
                    'track_id': track_info['id'],  # Track ID
                    'album': track_info['album']['name'],  # Album name
                    'release_date': track_info['album']['release_date'],  # Release date
                    'duration_ms': track_info['duration_ms']  # Duration of the track
                }
                playlist_data.append(track_data)  # Add the track data to the list
        else:
            print(f"Failed to fetch tracks for playlist {playlist_id}: {response.text}")

    # Save the fetched track data to a JSON file
    with open('tracks.json', 'w') as tracks_file:
        json.dump(track_data_list, tracks_file)

    # Save the track data to a CSV file
    print(f"Saving CSV to: {os.getcwd()}")
    df = pd.DataFrame(playlist_data)  # Convert the data to a DataFrame
    df.to_csv('playlist_songs.csv', index=False)  # Save the DataFrame as a CSV
    print(df)  # Print the DataFrame for verification

    return df  # Return the DataFrame for further use if needed

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
