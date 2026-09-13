# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
import re, os

with open(os.path.join("manase_butcher", "__init__.py")) as f:
    version = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)', f.read()).group(1)

setup(
    name="manase_butcher",
    version=version,
    description="MANASE BUTCHER - fish supplier & multi-branch butcher management for ERPNext v16",
    author="MANASE BUTCHER",
    author_email="dev@manasebutcher.co.tz",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    python_requires=">=3.10",
)
