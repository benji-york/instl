import sys
import os
from pathlib import Path
import unittest
import subprocess
import stat
import ctypes
import io
import contextlib
import filecmp
import random
import string
from collections import namedtuple

import utils
from pybatch import *
from pybatch import PythonBatchCommandAccum
from pybatch.downloadBatchCommands import DownloadFiles
from configVar import config_vars

current_os_names = utils.get_current_os_names()
os_family_name = current_os_names[0]
os_second_name = current_os_names[0]
if len(current_os_names) > 1:
    os_second_name = current_os_names[1]

config_vars["__CURRENT_OS_NAMES__"] = current_os_names

from .test_PythonBatchBase import *

"""
    Tests in the file are preformed against apache.org SVN servers.
    This is done to make sure the python-batch svn code is general and does not depend on any
    peculiarities of particular private svn server.

    However apache.org SVN servers require manual confirmation of the server certificate.

    To do that run the following command on the machien where the test will run:

    svn info https://svn.apache.org/repos/asf/subversion/trunk --depth=immediates

    if the question comes up:

    (R)eject, accept (t)emporarily or accept (p)ermanently?

    choose p

"""


class TestDownloadBatch(unittest.TestCase):
    def __init__(self, which_test):
        super().__init__(which_test)
        self.pbt = TestPythonBatch(self, which_test)

    @unittest.skipUnless(running_on_Mac, "Mac only test")
    def setUp(self):
        self.pbt.setUp()

    def tearDown(self):
        self.pbt.tearDown()

    def test_download_repr(self):
        self.pbt.reprs_test_runner(DownloadFiles(url_to_path={
            "https://d2eg57cquawzwn.cloudfront.net/V13/00/02/Common/Data/Instrument%20Data/NKS/Grand%20Rhapsody/PAResources/dist_database/Waves/Grand%20Rhapsody%20Piano%20Stereo/color.json"
            : "python_batch_test_results/TestDownloadBatch/Download/color.json",
            "https://d2eg57cquawzwn.cloudfront.net/V13/01/32/Common/Data/Instrument%20Data/NKS/Grand%20Rhapsody/Grand%20Rhapsody%20Stereo/Grand%20Rhapsody%20Init.nksf":
            "python_batch_test_results/TestDownloadBatch/Download/blas.nksf"
        },
            cookie=f"""\"CloudFront-Key-Pair-Id=APKAI3XDGLX25XNO6R5Q;CloudFront-Policy=eyJTdGF0ZW1lbnQiOiBbeyJSZXNvdXJjZSI6Imh0dHBzOi8vZDJlZzU3Y3F1YXd6d24uY2xvdWRmcm9udC5uZXQvKiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTY0MDY5Nzg2MX0sIkRhdGVHcmVhdGVyVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNjQwNjkxNTYxfX19XX0_;CloudFront - Signature = HE6lXL3F2SBCfYOX6L5BpXEsIH19YefUNEpGLJ8~kdn9zUtGRtwmIqPdX1nwYGMj2XpAktvKB26vemy7alGU7HM0tGDpGcr63aNWROWxAhrePbEvOmUH650wAyuwJgOREtJY - MtcmsbXW2FMXWUpPAPmvwy3YTTuWze3ypnLZ9dHS5XiWDFwLw0X3QcRf4X1lezHi5eGXxfu0hKSRYqDWfaaaO1 - jfk1YWMWXoF6Y0S8rjoNB7BQTEmpdi6ldylNiN26bUUZoz1ZXUiIpT7c2p0TzZM2fo0UXKVv29~NLHqYj2bZTD5ToPOqbMQOH6SNyN6tfJXlmm31Nf4x4hXKNg__\""""

        ))

    def test_Download(self):
        self.pbt.batch_accum.clear(section_name="doit")
        with self.pbt.batch_accum.sub_accum(Stage("bla bla")) as sub_bc:
            sub_bc += DownloadFiles(url_to_path={"https://d2eg57cquawzwn.cloudfront.net/V13/00/02/Common/Data/Instrument%20Data/NKS/Grand%20Rhapsody/PAResources/dist_database/Waves/Grand%20Rhapsody%20Piano%20Stereo/color.json":
                                                    "/Users/orenc/playground/color.json", "https://d2eg57cquawzwn.cloudfront.net/V13/01/32/Common/Data/Instrument%20Data/NKS/Grand%20Rhapsody/Grand%20Rhapsody%20Stereo/Grand%20Rhapsody%20Init.nksf": "/Users/orenc/playground/blas.nksf"},
                                    cookie_input=r"d2eg57cquawzwn.cloudfront.net:CloudFront-Key-Pair-Id=APKAI3XDGLX25XNO6R5Q;CloudFront-Policy=eyJTdGF0ZW1lbnQiOiBbeyJSZXNvdXJjZSI6Imh0dHBzOi8vZDJlZzU3Y3F1YXd6d24uY2xvdWRmcm9udC5uZXQvKiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTY0MDg1NjE1Mn0sIkRhdGVHcmVhdGVyVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNjQwODQ5ODUyfX19XX0_;CloudFront-Signature=SG9BAQRuGNk84Xr7qaYL0rVeseXBXyp5qF1EkUO-tB62yDvlJoxJHrARzVXLvQ5GUv4Mv0G1qpI2YU4z6TIomoOEUS4TOW3OJDdCrjQVP2R53q35kvBj-XoXd8i9AKUdVdjmft58WxhFojRKbqbpnrjFygGTOMr2eVrDLmhINZ5mkmqg6EuK~544YZ0fDii2iIWTqOXh8gBS2UDhS~bqOFpvWwAOY0nGYVylZrs9qwMWcwTlaNnz6TnPIcIza08T8b2XeqCkjuuMwQ8J9lFiXHDBV6bdNzBWaHAt4Pn-UarZvykj-QO7bIba8CWbkPIJJveWPsE5z3xbx3qg7uVc2g__")

        self.pbt.exec_and_capture_output()

