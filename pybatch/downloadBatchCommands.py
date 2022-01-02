import json
from typing import List
from pathlib import Path

import requests
from http.cookies import SimpleCookie

from requests.cookies import cookiejar_from_dict

from configVar import config_vars
from .baseClasses import PythonBatchCommandBase
from .fileSystemBatchCommands import MakeDir
import utils


class DownloadFiles(PythonBatchCommandBase):
    def __init__(self, url_to_path: dict = None, cookie_input: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.url_path_dict = url_to_path
        self.cookie = cookie_input

    def repr_own_args(self, all_args: List[str]) -> None:
        if self.url_path_dict:
            complete_repr = f"url_to_path=" + json.dumps(self.url_path_dict)
            all_args.append(complete_repr)
        if self.cookie:
            all_args.append(f"cookie_input=\"{self.cookie}\"")

    def progress_msg_self(self):
        the_progress_msg = f"Downloading files'"  # todo  - think how it should be done
        return the_progress_msg

    @staticmethod
    def get_cookie_dict_from_str(cookie_input):
        cookie_str = cookie_input or config_vars["COOKIE_JAR"].str()
        cookie = SimpleCookie()
        cookie.load(cookie_str)
        cookies = {}
        for key, morsel in cookie.items():
            if ":" in key:
                key = key.split(":")[1]
            cookies[key] = morsel.value
        return cookies

    def build_url_path_dict(self, name):  # todo - should add dict transformation
        bla = dict([i.split(':') for i in config_vars[name].str()])
        return bla

    def __call__(self, *args, **kwargs):
        PythonBatchCommandBase.__call__(self, *args, **kwargs)
        with requests.Session() as dl_session:
            # get_cookie_dict_from_str

            cookies = self.get_cookie_dict_from_str(self.cookie)
            if not self.url_path_dict:
                #self.url_path_dict = self.build_url_path_dict("PATH_FILE_LIST")
                self.url_path_dict = config_vars['PATHS'].dict()
            dl_session.cookies = cookiejar_from_dict(cookies)
            for url, path in self.url_path_dict.items():
                url = config_vars.resolve_str(url)
                path = Path(config_vars.resolve_str(path))
                if path.is_dir():
                    filename = Path(url.split("/").pop())
                    path = path.joinpath(filename)
                with MakeDir(path.parent, report_own_progress=False) as dir_maker:
                    dir_maker()
                with open(path, "wb") as fo:
                    timeout_seconds = int(config_vars.get("CURL_MAX_TIME", 480))
                    super().increment_and_output_progress(increment_by=0,
                                                          prog_msg=f"downloaded {path}")
                    read_data = dl_session.get(url, timeout=timeout_seconds)
                    read_data.raise_for_status()  # must raise in case of an error. Server might return json/xml with error details, we do not want that
                    fo.write(read_data.content)


class DownloadFileAndCheckChecksum(DownloadFiles):
    def __init__(self, url, path, checksum, **kwargs) -> None:
        super().__init__(url, path, **kwargs)
        self.checksum = checksum

    def repr_own_args(self, all_args: List[str]) -> None:
        super(DownloadFileAndCheckChecksum, self).repr_own_args(*all_args)
        all_args.append(self.unnamed__init__param(self.checksum))

    def progress_msg_self(self):
        super(DownloadFileAndCheckChecksum, self).progress_msg_self()

    def __call__(self, *args, **kwargs):
        PythonBatchCommandBase.__call__(self, *args, **kwargs)
        try:
            DownloadFiles.__call__(self, *args, **kwargs)
            checksum_ok = utils.check_file_checksum(self.path, self.checksum)
            if not checksum_ok:
                raise ValueError(f"bad checksum for {self.path} even after re-download")
        except Exception as ex:
            raise
