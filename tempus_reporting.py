from __future__ import print_function
import os.path
from io import BytesIO, StringIO
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import shutil
import paramiko
import logging
import logging.handlers

def transfer_file(fid, gserv):
    request = gserv.files().get_media(fileId=fid['id'])
    fh = BytesIO()

    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print("Download %s %d%%." % (fid['name'], int(status.progress() * 100)))

    s=str(fh.getvalue(),'utf-8')
    data = StringIO(s)
    df = pd.read_csv(data)
    df = df.replace({'-': ''})
    df = df[df['sample_barcode'] != '']
    #df.to_csv(file_id['name'], index=False)
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)

    """
    Connect to sftp and transfer file
    """
    #sftp -i keys/medio_tempus_customer medio_tempus_customer@sftp.precisemdx.com
    #cd Results
    #put 211208_0802_Brainworks_COVIDStatusFile.csv
    sftp_key_file = "./keys/medio_tempus_customer"
    k = paramiko.RSAKey.from_private_key_file(sftp_key_file)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect( hostname = "sftp.precisemdx.com", username = "medio_tempus_customer", pkey = k )

    sftp = c.open_sftp()
    # check the Results are in list
    if ("Results" not in sftp.listdir()):
        raise
    sftp.chdir("Results")
    # check that Processed is in list
    if ("Processed" not in sftp.listdir()):
        raise

    #sftp.put(file_id["name"], file_id["name"])
    with sftp.open(file_id["name"], mode="w") as remote_file:
        csv_buffer.seek(0)
        shutil.copyfileobj(csv_buffer, remote_file)
    remote_file.close()

    if (file_id["name"] not in sftp.listdir()):
        raise
    info = sftp.stat(file_id["name"])
    if( csv_buffer.tell() != info.st_size ):
        raise

    sftp.close()
    c.close()

def main():
    """
    Read in Prior processed files, don't repeat
    """
    posted = open('posted', 'r')
    lines_posted = posted.readlines()
    lines_posted = [x.strip() for x in lines_posted]
    failed = open('failed', 'r')
    lines_failed = failed.readlines()
    lines_failed = [x.strip() for x in lines_failed]
    prior_processed = lines_posted + lines_failed
    posted.close()
    failed.close()

    # Add email error logging
    smtp_handler = logging.handlers.SMTPHandler(mailhost=("aspmx.l.google.com", 25),
                                                fromaddr="matt@medio.ai",
                                                toaddrs="matt@medio.ai",
                                                subject=u"AppName error!")

    logger = logging.getLogger()
    logger.addHandler(smtp_handler)

    try:
        """
        Connect to Google Drive for file download
        """
        since_date = '2021-12-08T18:00:00'
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        key_file_location = "keys/tempus-333620-4cbcf1e6cef8.json"
        credentials = Credentials.from_service_account_file(key_file_location, scopes=SCOPES)

        service = build('drive', 'v3', credentials=credentials)

        results = service.files().list(
            pageSize=12,
            fields="nextPageToken, files(id, name)",
            q="modifiedTime > '" + since_date + "'"
            ).execute()
        items = results.get('files', [])

        #file_id = items.pop()
        for file_id in reversed(items):
            if file_id['name'] in prior_processed:
                print("Skipping: " + file_id['name'])
                continue

            print("Processing: " + file_id['name'])

            transfer_file(file_id, service)

            posted = open('posted', 'a')
            posted.write(file_id["name"])
            posted.write('\n')
            posted.close()

    except Exception as e:
      print("exception")
      failed = open('failed', 'a')
      failed.write(file_id["name"])
      failed.write('\n')
      failed.close()
      #logger.exception('Unhandled Exception')


if __name__ == '__main__':
    main()
