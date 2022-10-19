"""Main script to execute directly."""

import logging

from time import sleep

from envidat.api.v1 import get_metadata_list
from envidat.metadata import Record
from envidat.s3.bucket import Bucket
from envidat.utils import get_logger, load_dotenv_if_in_debug_mode


log = logging.getLogger(__name__)


def main():
    """For direct execution of file."""
    load_dotenv_if_in_debug_mode(env_file=".env.secret")
    get_logger()

    log.info("Starting main nasa-gcmd script.")

    packages_in_ckan = get_metadata_list()

    s3_bucket = Bucket(bucket_name="nasa", is_new=True, is_public=True)
    packages_in_s3 = s3_bucket.list_dir(names_only=True)

    missing_packages = list(set(packages_in_ckan) - set(packages_in_s3))
    log.info(f"Found {len(missing_packages)} missing packages in bucket.")

    for package_name in missing_packages:
        xml_str = Record(package_name, convert="xml").content
        s3_bucket.put(f"{package_name}.xml", xml_str)
        # Take it easy on the API!
        log.debug("Sleeping 5 seconds...")
        sleep(5)

    s3_bucket.configure_static_website()
    package_xml_list = [f"{package_name}.xml" for package_name in packages_in_ckan]
    s3_bucket.generate_index_html("EnviDat NASA XML", package_xml_list)

    log.info("Finished main nasa-gcmd script.")


if __name__ == "__main__":
    main()
