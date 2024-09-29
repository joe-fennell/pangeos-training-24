import sys
import requests
import os

# add the filenames and google drive IDs required below:

file_ids = {
    'Milton_Keynes_labels.gpkg': '1CZDNtSgMJpGt6TODydgK3KM2_euoN8X6',
    'Milton_Keynes_aerial_VisVNIR.nc': '18qwWje55m1Kt2AKrJHeqNTk_cBa-BY9a',
    'Milton_Keynes_aerial_SWIR.nc': '1sGtxaEIqlZ80VYRfZUUEdOC9_Hp4THkh',
    'Milton_Keynes_Sentinel2_L2A.nc': '1SzurMfuv5IsbP5ekqE6IUj6jGpdQrEPZ',
    'Milton_Keynes_Sentinel2_L1C.nc': '1AFXr2s15aIzRt2-3jcJqhYa-TqucPLEF',
}

file_paths = [os.path.join('data', x) for x in file_ids.keys()]

DST_DIR = os.path.join(os.path.dirname(__file__), 'data')

# do not edit below

def _download_file_from_google_drive(file_id, destination):

    def save_response_content(response, destination):
        CHUNK_SIZE = 32768

        with open(destination, "wb") as f:
            for chunk in response.iter_content(CHUNK_SIZE):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
    
    URL = f'https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t'

    session = requests.Session()

    response = session.get(URL)
    
    if response.reason == 'OK':
        save_response_content(response, destination)
        return None
    
    if response.reason == 'Not Found':
        raise ValueError(f'{file_id} not found on Google Drive - check the File ID')
    
    raise RuntimeError(f'{file_id} could not be downloaded')


def download():
    total = len(file_ids)
    current = 1
    for fname, fid in file_ids.items():
        destination = os.path.join(DST_DIR, fname)
    
        print(f'Downloading {fname}... ({current}/{total})')
    
        _download_file_from_google_drive(fid, destination)
        current += 1
    print(f'All files downloaded to {DST_DIR}')


if __name__ == "__main__":
    download()
