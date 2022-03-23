import os
import sys
import logging
import requests
import boto3

from io import BytesIO
from textwrap import dedent
from time import sleep
from botocore.config import Config


log = logging.getLogger(__name__)


def _download_s3_object_to_memory(
    path: str, bucket: "boto3.resource.Bucket"
) -> BytesIO:
    """
    Download an S3 object into a binary memory file.

    To use:
    download_s3_object_to_memory(
        "index.html"
    ).read().decode("utf_8")

    """

    log.debug(f"Attempting download of key: {path} to memory.")
    file = bucket.Object(path)
    buf = BytesIO()
    file.download_fileobj(buf)
    buf.seek(0)

    return buf


def _get_url(url: str) -> requests.Response:
    "Helper wrapper to get a URL with additional error handling."

    try:
        log.debug(f"Attempting to get {url}")
        r = requests.get(url)
        r.raise_for_status()
        return r
    except requests.exceptions.ConnectionError as e:
        log.error(f"Could not connect to internet on get: {r.request.url}")
        log.error(e)
    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP response error on get: {r.request.url}")
        log.error(e)
    except requests.exceptions.RequestException as e:
        log.error(f"Request error on get: {r.request.url}")
        log.error(f"Request: {e.request}")
        log.error(f"Response: {e.response}")
    except Exception as e:
        log.error(e)
        log.error(f"Unhandled exception occured on get: {r.request.url}")

    return None


def get_logger() -> logging.basicConfig:
    "Set logger parameters with log level from environment."

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", default="DEBUG"),
        format=(
            "%(asctime)s.%(msecs)03d [%(levelname)s] "
            "%(name)s | %(funcName)s:%(lineno)d | %(message)s"
        ),
        datefmt="%y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def get_s3_bucket(bucket_name: str = None) -> "boto3.resource.Bucket":
    "Get an S3 bucket using S3 credentials in environment."

    log.debug(f"Initialise S3 client with endpoint: {os.getenv('AWS_ENDPOINT')}")
    s3 = boto3.resource(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
        endpoint_url=os.getenv("AWS_ENDPOINT"),
        region_name=os.getenv("AWS_REGION", default=""),
        config=Config(signature_version="s3v4"),
    )
    if bucket_name is None:
        bucket_name = os.getenv("AWS_BUCKET_NAME")

    try:
        bucket = s3.Bucket(bucket_name)
    except Exception as e:
        log.error(e)
        log.error(f"Failed to access bucket named: {bucket_name}")
        bucket = None

    return bucket


def get_package_list_from_ckan(host: str = None) -> list:
    "Get package list from CKAN API, with given host url."

    if host is None:
        host = os.getenv("CKAN_HOST", default="https://www.envidat.ch")

    log.info(f"Getting package list from {host}.")
    try:
        package_names = _get_url(f"{host}/api/3/action/package_list").json()
    except AttributeError as e:
        log.error(e)
        log.error(f"Getting package names from CKAN failed. Returned: {package_names}")
        raise AttributeError("Failed to extract package names as JSON.")

    log.debug("Extracting [result] key from JSON.")
    package_names = list(package_names["result"])

    return package_names


def transfer_package_xml_to_s3(
    package_name: str, bucket: "boto3.resource.Bucket", host: str = None
):
    "Download package XMLs from CKAN host and upload to specific S3 bucket."

    if host is None:
        host = os.getenv("CKAN_HOST", default="https://www.envidat.ch")
    url = f"{host}/dataset/{package_name}/export/gcmd_dif.xml"
    log.debug(f"CKAN url to download: {url}")
    data = _get_url(url).content

    log.debug(f"Attempting upload of {package_name}.xml to S3 bucket.")

    try:
        bucket.upload_fileobj(BytesIO(data), f"{package_name}.xml")
        log.info(f"Successful upload: {package_name}.xml")
    except Exception as e:
        log.error(e)
        log.error(f"Failed to upload XML for: {package_name}")
        return False

    return True


def generate_index_html(package_names: list) -> BytesIO:
    "Write index.html to root of S3 bucket, with embedded S3 download links."

    buf = BytesIO()

    # Start HTML
    html_block = dedent(
        """
        <html>
        <head>
        <meta charset="utf-8">
        <title>EnviDat Metadata List</title>
        </head>
        <body>
        """
    ).strip()
    log.debug(f"Writing start HTML block to buffer: {html_block}")
    buf.write(html_block.encode("utf_8"))

    # Packages
    log.info("Iterating package list to write S3 links to index.")
    for package_name in package_names:
        log.debug(f"Package name: {package_name}")
        html_block = dedent(
            f"""
            <div class='flex py-2 xs6'>
            <a href='https://nasa.s3-zh.os.switch.ch/{package_name}.xml'>
                https://nasa.s3-zh.os.switch.ch/{package_name}.xml
            </a>
            </div>"""
        )
        log.debug(f"Writing package link HTML to buffer: {html_block}")
        buf.write(html_block.encode("utf_8"))

    # Close
    html_block = dedent(
        """
        </body>
        </html>"""
    )
    log.debug(f"Writing end HTML block to buffer: {html_block}")
    buf.write(html_block.encode("utf_8"))

    # Reset read pointer.
    # DOT NOT FORGET THIS, for reading afterwards!
    buf.seek(0)

    return buf


def main():
    "Main script logic."

    get_logger()

    bucket = get_s3_bucket()
    packages_in_ckan = get_package_list_from_ckan()
    packages_in_s3 = [os.path.splitext(file.key)[0] for file in bucket.objects.all()]
    missing_packages = list(set(packages_in_ckan) - set(packages_in_s3))
    log.info(f"Found {len(missing_packages)} missing packages in bucket.")

    for package_name in missing_packages:
        transfer_package_xml_to_s3(package_name, bucket)
        # Take it easy on the API!
        log.debug("Sleeping 5 seconds...")
        sleep(5)

    # Create index.html
    index_html = generate_index_html(packages_in_ckan)
    log.info("Uploading generated index.html to S3 bucket.")
    bucket.upload_fileobj(index_html, "index.html")
    log.info("Done.")


if __name__ == "__main__":
    main()
