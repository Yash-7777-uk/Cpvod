from flask import Flask, request, jsonify
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import requests
from bs4 import BeautifulSoup
import os
import glob

app = Flask(__name__)

def wvd_check():
    extracted_device = glob.glob(f'{os.getcwd()}/WVDs/*.wvd')[0]
    return extracted_device

# Function to generate DRM keys
def generate_drm_keys(video_url):
    wvd = wvd_check()

    headers = {
        'x-access-token': 'eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6NDU4MDU2OCwib3JnSWQiOjEsInR5cGUiOjEsIm1vYmlsZSI6IjkxNzAzMjQyNzc1OCIsIm5hbWUiOiJqYW1lcyIsImVtYWlsIjoic3VicmF2ZXRpQGNsYXNzcGx1cy5jbyIsImlzSW50ZXJuYXRpb25hbCI6MCwiZGVmYXVsdExhbmd1YWdlIjoiZW4iLCJjb3VudHJ5Q29kZSI6IklOIiwiY291bnRyeUlTTyI6IjkxIiwidGltZXpvbmUiOiJHTVQrNTozMCIsImlhdCI6MTY0NDQ3MjEwMywiZXhwIjoxNjQ2MjAwMTAzfQ.2mD_39uZJE5tqp64lPSKEUvQrHZjYJ2KN6WPHgJlEHRSeHtiMycG4bTfOv3ra1g_'
    }

    response = requests.get(f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={video_url}', headers=headers).json()

    if response['status'] != 'ok':
        return {"error": "Failed to fetch DRM URLs"}

    mpd = response['drmUrls']['manifestUrl']
    lic = response['drmUrls']['licenseUrl']
    mpd_response = requests.get(mpd)
    soup = BeautifulSoup(mpd_response.text, 'xml')

    uuid = soup.find('ContentProtection', attrs={'schemeIdUri': 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed'})
    pssh = uuid.find('cenc:pssh').text

    ipssh = PSSH(pssh)
    device = Device.load(wvd)
    cdm = Cdm.from_device(device)
    session_id = cdm.open()
    challenge = cdm.get_license_challenge(session_id, ipssh)
    licence = requests.post(lic, data=challenge, headers=headers)
    licence.raise_for_status()

    cdm.parse_license(session_id, licence.content)

    keys = []
    for key in cdm.get_keys(session_id):
        if key.type != 'SIGNING':
            keys.append(f'{key.kid.hex}:{key.key.hex()}')

    cdm.close(session_id)

    return {"mpd_url": mpd, "keys": keys}

# API endpoint
@app.route('/api', methods=['GET'])
def api():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400

    try:
        result = generate_drm_keys(video_url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)