import os
import logging

from time import sleep

from envidat.api.v1 import get_metadata_list, _get_url
from envidat.s3.bucket import Bucket
from envidat.utils import get_logger, load_dotenv_if_in_debug_mode


log = logging.getLogger(__name__)


def get_ckan_package_xml(
    package_name: str,
):
    "Download package XML from CKAN host."

    # TODO remove function and generate XML manually
    host = os.getenv("API_URL", default="https://www.envidat.ch")
    url = f"{host}/dataset/{package_name}/export/gcmd_dif.xml"
    log.debug(f"CKAN url to download: {url}")
    return _get_url(url).content


def main():
    "Main script logic."

    load_dotenv_if_in_debug_mode(env_file=".env.secret")
    get_logger()

    log.info("Starting main nasa-gcmd script.")

    packages_in_ckan = get_metadata_list()

    s3_bucket = Bucket(bucket_name="nasa", is_new=True, is_public=True)
    packages_in_s3 = s3_bucket.list_dir(names_only=True)

    missing_packages = list(set(packages_in_ckan) - set(packages_in_s3))
    log.info(f"Found {len(missing_packages)} missing packages in bucket.")

    for package_name in missing_packages:
        xml = get_ckan_package_xml(package_name)
        s3_bucket.put(f"{package_name}.xml", xml)
        # Take it easy on the API!
        log.debug("Sleeping 5 seconds...")
        sleep(5)

    s3_bucket.configure_static_website()
    package_xml_list = [f"{package_name}.xml" for package_name in packages_in_ckan]
    s3_bucket.generate_index_html("EnviDat NASA XML", package_xml_list)

    log.info("Finished main nasa-gcmd script.")


if __name__ == "__main__":
    main()
