import requests
import json
import os
import sys
from urllib.parse import urlparse
import concurrent.futures
import datetime
import argparse
from tqdm import tqdm


def download_archive(input_list):
    _, file_timestamp, file_url, file_type, _, _, file_length = input_list
    
    # check if already downloaded
    file_url_parsed = urlparse(file_url)

    file_path, file_name = os.path.split(file_url_parsed.path)
    file_path = os.path.join("output", base_domain, file_timestamp, *file_path.split('/'))

    if file_name == '':
        file_name = 'index.html'

    # construct download url
    download_url = f'https://web.archive.org/web/{file_timestamp}/{file_url}'

    if os.path.exists(os.path.join(file_path, file_name)):
        #print(f"\nexists: {download_url} to  {file_path}/{file_name}")
        return False

    # download file
    r = requests.get(download_url)

    # create directory structure
    os.makedirs(file_path, exist_ok=True)

    print(f"\nloaded: {download_url} to {file_path}/{file_name} ")
    # save file
    with open(os.path.join(file_path, file_name), 'wb') as f:
        f.write(r.content)
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Usage: "python wbmdownloader.py http://example.com" ')

    parser.add_argument('url', type=str, help='The website or path to download. e.g. "http://example.com."')
    parser.add_argument('--from', dest='tsfrom', type=int, help="Starting date to download. Timestamp in format YYYYMMDD, e.g. 20120808")
    parser.add_argument('--to', dest='tsto', type=int, help="End date to download. Timestamp in format YYYYMMDD, e.g. 20120808")
    parser.add_argument('--threads', dest='threads', type=int, help="Number of concurrent downloads. Recommended 4 - 8")
    parser.add_argument('--list', dest='onlyjson', action='store_true', default=False, help='Do not download, only store results as json file')
    parser.add_argument('--exact-url', dest='exact', action='store_true', default=False, help='Download only the url provied and not the full site')
    parser.add_argument('--all-types', dest='alltypes', action='store_true', default=False, help='Download all file types')
    parser.add_argument('--all-codes', dest='allcodes', action='store_true', default=False, help='Download all status codes (3xx, 4xx)')
    parser.add_argument('--filter', dest='customfilt', type=str, help="Custom regex filter in the format 'field:regex'. E.g. only urls that are html files: 'original:.*html'")
    parser.add_argument('--json', dest='json_path', type=str, help="Custom json file with urls'")
    parser.add_argument('--mime', dest='mime', type=str, help="Custom mime'")
    args = parser.parse_args()

    if args.url is None:
        sys.exit(0)
    else: base_url = args.url

    if base_url.startswith('http'):
        base_domain = urlparse(base_url).netloc
    else: 
        base_domain = urlparse(base_url).path

    print(base_domain)
    if args.tsfrom is None:
        ts_from = datetime.date.today() - datetime.timedelta(days=365)
        ts_from = int(ts_from.strftime('%Y%m%d'))
        print(f'No from timestamp chosen. Automatically set to: {ts_from}')
    else: ts_from = args.tsfrom

    if args.tsto is None:
        ts_to = int(datetime.date.today().strftime('%Y%m%d'))
        print(f'No to timestamp chosen. Automatically set to: {ts_to}')
    else: ts_to = args.tsto

    if args.threads is None:
        print('Not using concurrency')
        n_threads = 1
    else: n_threads = args.threads

    request_url =  "https://web.archive.org/cdx/search/xd"
    

    payload = {'collapse': 'digest',
                'gzip': "false",
                'output': 'json',
                'from': ts_from,
                'to': ts_to,
                }
    
    if args.exact:
        payload['url'] = f"https://{base_url}"
    else:
        if not base_url.endswith('/'):
            #base_url += '/'
            pass
        payload['url'] = base_url + '*'

    filter_list = []

    if args.allcodes is not True:
        filter_list.append('statuscode:200')

    if args.alltypes is not True:
        if args.mime:
            filter_list.append(f'mimetype:{args.mime}')
        else:
            filter_list.append('mimetype:text/html')
    
    if args.customfilt is not None:
        filter_list.append(args.customfilt)
        
    if len(filter_list) > 0:
        payload['filter'] = filter_list

    print(f'Parameters: {payload}')

    print('Requesting Index...')

    json_path = os.path.join('output', base_domain + '.json')


    if args.json_path:
        json_path = args.json_path


    if not os.path.exists(json_path):
        r = requests.get(request_url, params=payload)

        if r.status_code != 200:
            print('Bad response!')
            print('Status code:')
            print(r.status_code)
            print('Headers')
            print(r.headers)
            print('Content')
            print(r.content)
            sys.exit(1)

        print('Got response!')
        print(r.status_code)

        json_response = r.json()
        if len(json_response) == 0:
            print('No results... maybe url wrong? Maybe timestamps too narrow?')

        download_list = json_response[1:]
        print(f'Got {len(download_list)} to download...')
        if args.onlyjson is True or True:
            os.makedirs(os.path.join('output'), exist_ok=True)
            with open(json_path, 'w') as f:
                f.write(json.dumps(json_response, indent=4, sort_keys=True))
            print(f'List output stored to: {os.path.join("output", base_domain + ".json")}')
            #sys.exit(0)

    else:

        with open(json_path, 'rb') as f:
            download_list = json.load(f)[1:]
    urls = dict()
    for x in download_list:
        #print(x)
        key  = x[0]
        date = x[1]
        if key not in urls:
            urls[key] = x
        if key in urls and urls[key][1] < x[1]:
            dates = (x[1], urls[key][1])
            urls[key] = x

    download_list2 = list()
    for x in urls:
        download_list2.append(urls[x])

    import random


    #random.shuffle(download_list2)

    with tqdm(total=len(download_list2), unit='urls') as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = {executor.submit(download_archive, url): url for url in download_list2}
            for future in concurrent.futures.as_completed(futures):
                future.result()
                pbar.update(1)
    print('Done!')
