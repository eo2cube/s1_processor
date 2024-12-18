import logging
from .s1_slc_proc import S1_SLC_proc
from .download_ASF import asf_downloader
import tomli

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)

def process(config_file):
    with open(config_file, "rb") as conf:
        config = tomli.load(conf)

    download = {**config["General"], **config["Download"]}
    if download["download"] is True:
        download.pop("download", None)
        asf_downloader(**download)

    proc = {**config["General"], **config["Processing"]}

    S1_SLC_proc(**proc)
