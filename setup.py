#!/usr/bin/env python
import pathlib
import sys

from setuptools import find_packages, setup

__author__ = "Gavin Huttley"
__copyright__ = "Copyright 2021-date, Gavin Huttley"
__credits__ = ["Gavin Huttley"]
__license__ = "BSD"
__version__ = "2021.04.01"
__maintainer__ = "Gavin Huttley"
__email__ = "Gavin.Huttley@anu.edu.au"
__status__ = "Development"

# Check Python version, no point installing if unsupported version inplace
if sys.version_info < (3, 6):
    py_version = ".".join([str(n) for n in sys.version_info])
    raise RuntimeError(
        "Python-3.6 or greater is required, Python-%s used." % py_version
    )

short_description = "homologsampler"

# This ends up displayed by the installer
readme_path = pathlib.Path(__file__).parent / "README.rst"

long_description = readme_path.read_text()

PACKAGE_DIR = "src"

setup(
    name="homologsampler",
    version=__version__,
    author="Gavin Huttley",
    author_email="gavin.huttley@anu.edu.au",
    description=short_description,
    long_description=long_description,
    long_description_content_type="text/x-rst",
    platforms=["any"],
    license=["BSD-3"],
    keywords=["science", "bioinformatics", "genetics", "evolution"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: BSD",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(where=PACKAGE_DIR),
    package_dir={"": PACKAGE_DIR},
    install_requires=[
        "cogent3",
        "ensembldb3",
        "scitrack",
        "click",
    ],
    entry_points={
        "console_scripts": [
            "homolog_sampler=homologsampler.__init__:cli",
        ],
    },
    url="https://github.com/cogent3/homologsampler",
    extras_require={"mysql": ["PyMySQL", "sqlalchemy"]},
)
