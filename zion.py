import sys
import json
import os
import argparse
import requests
from urllib.parse import quote
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_autoinstaller
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload


BASE_URL = 'https://webexapis.com/v1'
scopes = ["https://www.googleapis.com/auth/youtube.upload"]
uri = "https%3A%2F%2Fmtzioncary.org"

def get_authorization_code(client_id, username, password):
    """
    Uses Selenium to log in and get the Webex authorization code from the URL
    """
    url = BASE_URL + '/authorize' + f'?response_type=code&client_id={client_id}&redirect_uri={uri}&scope=meeting%3Arecordings_read%20spark%3Akms&state=whj'

    try:
        options = Options()
        options.add_argument("--headless")
        chromedriver_autoinstaller.install()
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(30)
        driver.get(url)
        driver.find_element_by_name("IDToken1").send_keys(username)
        driver.find_element_by_id("IDButton2").click()
        driver.find_element_by_name("IDToken2").send_keys(password)
        driver.find_element_by_id("Button1").click()
        url_code = driver.current_url
        code = url_code.split('?')[1].split('&')[0].split('=')[1]
        driver.close()
    except Exception as err:
        driver.close()
        raise Exception('ERROR Getting WebEx authorization code: ' + str(err))
    
    return code

def get_access_token(client_id, client_secret, code):
    """
    Get the Webex access token
    """
    url = BASE_URL + '/access_token'
    headers = {
    'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'grant_type': 'authorizztion_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'redirect_uri': uri
    }
    try:
        response = requests.post(url, params=params, headers=headers)
        response.raise_for_status()
    except Exception as err:
        raise Exception('ERROR Getting WebEx access token: ' + str(err))
    json_response = response.json()
    return json_response['access_token']

def download_webex_video(token, video_file, date):
    """
    Download yesterday's video from Webex
    """
    url = BASE_URL + '/recordings'
    headers = {
        'timezone':'EST',
        'Authorization':'Bearer {}'.format(token)
    }
    list_params = f'?from={quote(date)}'

    try:
        response = requests.get(f'{url}{list_params}', headers=headers)
        response.raise_for_status()
        json_response = response.json()
        if json_response['items']:
            recording_id = json_response['items'][0]['id']
            response = requests.get(f'{url}/{recording_id}', headers=headers)
            response.raise_for_status()
            json_response = response.json()
            download_link = json_response['temporaryDirectDownloadLinks']['recordingDownloadLink']
            response = requests.get(download_link)
            response.raise_for_status()
            with open(video_file, 'wb') as f_h:
                f_h.write(response.content)
        else:
            raise Exception('ERROR There are no videos for this date')
    except Exception as err:
        raise Exception('ERROR Downloading recording from Webex: ' + str(err))

def upload_to_youtube(video_file, video_title, video_desc, date):
    """
    Upload video to YouTube
    """
    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "client_secrets.json"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build(api_service_name, api_version, credentials=credentials)

    title = f'{video_title} {date}'
    request = youtube.videos().insert(
        part="snippet,status",
        body={
          "snippet": {
            "categoryId": 22,
            "defaultLanguage": "en",
            "description": video_desc,
            "title": title
          },
          "status": {
            "privacyStatus": "public"
          }
        },
        media_body=MediaFileUpload(video_file)
    )
    response = request.execute()

    print(response)

def main(argv):
    if "WEBEX_CLIENT_ID" not in os.environ or "WEBEX_CLIENT_SECRET" not in os.environ or "WEBEX_USERNAME" not in os.environ or "WEBEX_PASSWORD" not in os.environ:
        print('Error: Make sure that WEBEX_CLIENT_ID, WEBEX_CLIENT_SECRET, WEBEX_USERNAME, WEBEX_PASSWORD env variables are set')
        exit(1)
    
    client_id = os.environ['WEBEX_CLIENT_ID']
    client_secret = os.environ['WEBEX_CLIENT_SECRET']
    username = os.environ['WEBEX_USERNAME']
    password = os.environ['WEBEX_PASSWORD']
    video_file = argv.metadata[0]
    recording_date = argv.metadata[1]
    video_title = argv.metadata[2]
    video_desc = argv.metadata[3]

    try:
        formatted_recording_date = datetime.fromisoformat(recording_date)
        date = datetime.isoformat(formatted_recording_date)
        print('Getting Webex authorization code...')
        authorization_code = get_authorization_code(client_id, username, password)
        print('Getting Webex access token...')
        access_token = get_access_token(client_id, client_secret, authorization_code)
        print('Downloading Webex video...')
        download_webex_video(access_token, video_file, date)
        print('Uploading video to YouTube...')
        upload_to_youtube(video_file, video_title, video_desc, datetime.strftime(formatted_recording_date, '%m-%d-%Y'))
        print('Done')
    except Exception as err:
        print(str(err))
        exit(1)


def arg_parse(args):
    parser = argparse.ArgumentParser(description='Download Webex video and upload to YouTube')
    parser.add_argument('metadata', metavar='S', type=str, nargs=4,
        help='zion <video file name> <date of recording in YYYY-MM-DD isoformat> <video title> <video description>')
    return parser.parse_args(args)

if __name__ == '__main__':
    main(arg_parse(sys.argv[1:]))