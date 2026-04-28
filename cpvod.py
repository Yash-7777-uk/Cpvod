import requests
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
from bs4 import BeautifulSoup
import os
import glob
import json
import traceback
from urllib.parse import urlparse
import lxml  # Make sure this is installed

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    banner = """
    ***************************************
    * ClassPlus DRM Key Extractor         *
    * Version: 1.2                        *
    ***************************************
    """
    print(banner)

def wvd_check():
    try:
        wvd_dir = os.path.join(os.getcwd(), 'WVDs')
        if not os.path.exists(wvd_dir):
            os.makedirs(wvd_dir)
        
        wvd_files = glob.glob(os.path.join(wvd_dir, '*.wvd'))
        if not wvd_files:
            raise FileNotFoundError("No .wvd files found in WVDs directory")
        
        print(f"[+] Found WVD file: {wvd_files[0]}")
        return wvd_files[0]
    except Exception as e:
        print(f"[-] WVD Error: {str(e)}")
        return None

def validate_url(url):
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            return False
        return url.startswith(('http://', 'https://'))
    except:
        return False

def get_video_info(url, headers):
    try:
        print("[+] Fetching video information...")
        api_url = f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}'
        response = requests.get(api_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[-] API Request Failed: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"Response Content: {e.response.text}")
        return None

def get_mpd_content(mpd_url):
    try:
        print("[+] Downloading MPD file...")
        response = requests.get(mpd_url, timeout=15)
        response.raise_for_status()
        
        # Check if content is actually MPD
        if not response.text.strip().startswith('<?xml') and '<MPD' not in response.text:
            raise ValueError("Response doesn't appear to be a valid MPD file")
            
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"[-] MPD Download Failed: {str(e)}")
        return None

def extract_pssh(mpd_content):
    try:
        print("[+] Parsing MPD for PSSH...")
        # Explicitly specify lxml as the parser
        soup = BeautifulSoup(mpd_content, 'lxml-xml')  # Note: using lxml-xml parser
        
        # Find all ContentProtection elements
        content_protections = soup.find_all('ContentProtection')
        if not content_protections:
            raise ValueError("No ContentProtection elements found in MPD")
        
        # Look for Widevine ContentProtection
        for cp in content_protections:
            if cp.get('schemeIdUri', '').lower() == 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed':
                pssh = cp.find('cenc:pssh')
                if pssh and pssh.string:
                    print("[+] Found Widevine PSSH")
                    return pssh.string.strip()
        
        raise ValueError("No valid Widevine PSSH found in MPD")
    except Exception as e:
        print(f"[-] PSSH Extraction Error: {str(e)}")
        return None

def get_decryption_keys(pssh, license_url, headers, wvd_path):
    try:
        print("[+] Initializing CDM session...")
        device = Device.load(wvd_path)
        cdm = Cdm.from_device(device)
        session_id = cdm.open()
        print(f"[+] Session ID: {session_id}")
        
        print("[+] Generating license challenge...")
        ipssh = PSSH(pssh)
        challenge = cdm.get_license_challenge(session_id, ipssh)
        
        print("[+] Sending license request...")
        license_headers = headers.copy()
        license_headers.update({
            'Content-Type': 'application/octet-stream',
            'Origin': 'https://web.classplusapp.com',
            'Referer': 'https://web.classplusapp.com/',
        })
        
        license_response = requests.post(
            license_url,
            data=challenge,
            headers=license_headers,
            timeout=15
        )
        license_response.raise_for_status()
        
        print("[+] Parsing license response...")
        cdm.parse_license(session_id, license_response.content)
        
        keys = []
        print("[+] Extracting keys...")
        for key in cdm.get_keys(session_id):
            if key.type != 'SIGNING':
                keys.append({
                    'kid': key.kid.hex(),
                    'key': key.key.hex(),
                    'type': key.type
                })
                print(f"  [+] Found key: {key.kid.hex()}:{key.key.hex()} ({key.type})")
        
        return keys
    except Exception as e:
        print(f"[-] Decryption Error: {str(e)}")
        return None
    finally:
        if 'session_id' in locals():
            cdm.close(session_id)
            print("[+] Closed CDM session")

def main():
    clear_screen()
    print_banner()
    
    # Configuration
    headers = {
        'x-access-token': 'eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6NDU4MDU2OCwib3JnSWQiOjEsInR5cGUiOjEsIm1vYmlsZSI6IjkxNzAzMjQyNzc1OCIsIm5hbWUiOiJqYW1lcyIsImVtYWlsIjoic3VicmF2ZXRpQGNsYXNzcGx1cy5jbyIsImlzSW50ZXJuYXRpb25hbCI6MCwiZGVmYXVsdExhbmd1YWdlIjoiZW4iLCJjb3VudHJ5Q29kZSI6IklOIiwiY291bnRyeUlTTyI6IjkxIiwidGltZXpvbmUiOiJHTVQrNTozMCIsImlhdCI6MTY0NDQ3MjEwMywiZXhwIjoxNjQ2MjAwMTAzfQ.2mD_39uZJE5tqp64lPSKEUvQrHZjYJ2KN6WPHgJlEHRSeHtiMycG4bTfOv3ra1g_',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # Get WVD file
    wvd_path = wvd_check()
    if not wvd_path:
        return
    
    # Get video URL
    video_url = input("[?] Enter video URL: ").strip()
    if not validate_url(video_url):
        print("[-] Invalid URL format. Please include http:// or https://")
        return
    
    try:
        # Step 1: Get video info
        video_info = get_video_info(video_url, headers)
        if not video_info:
            return
            
        if video_info.get('status') != 'ok':
            print("[-] API returned error status")
            print(json.dumps(video_info, indent=2))
            return
        
        # Step 2: Get MPD content
        mpd_url = video_info['drmUrls']['manifestUrl']
        license_url = video_info['drmUrls']['licenseUrl']
        
        print(f"[+] MPD URL: {mpd_url}")
        print(f"[+] License URL: {license_url}")
        
        mpd_content = get_mpd_content(mpd_url)
        if not mpd_content:
            return
        
        # Step 3: Extract PSSH
        pssh = extract_pssh(mpd_content)
        if not pssh:
            return
        
        # Step 4: Get decryption keys
        keys = get_decryption_keys(pssh, license_url, headers, wvd_path)
        if not keys:
            return
        
        # Display results
        print("\n[+] Successfully extracted keys:")
        print(f"\nMPD URL: {mpd_url}\n")
        for key in keys:
            print(f"--key {key['kid']}:{key['key']}")
        
        # Save to file
        with open('keys.txt', 'w') as f:
            f.write(f"MPD URL: {mpd_url}\n\n")
            for key in keys:
                f.write(f"--key {key['kid']}:{key['key']}\n")
        print("\n[+] Keys saved to keys.txt")
        
    except KeyboardInterrupt:
        print("\n[-] Process interrupted by user")
    except Exception as e:
        print(f"\n[-] Critical Error: {str(e)}")
        traceback.print_exc()
    finally:
        print("\n[+] Process completed")

if __name__ == "__main__":
    # Check for required packages
    try:
        import lxml
    except ImportError:
        print("[-] Error: lxml package is required. Install with: pip install lxml")
        exit(1)
    
    main()