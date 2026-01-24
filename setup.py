import os
from setuptools import setup, find_packages

long_description = ""
if os.path.exists("README.md"):
    with open("README.md", "r", encoding="utf-8") as readme:
        long_description = readme.read()

setup(
    name="rail-django",
    version="1.1.4",
    description="A Django wrapper framework with pre-configured settings and tools.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Milia Khaled",
    author_email="miliakhaled@gmail.com",
    url="https://github.com/raillogistic/rail-django",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Django>=5.0",
        "psycopg2>=2.9.9",
        "graphene-django>=3.1.5",
        "graphql-relay>=3.2.0",
        "django-filter>=23.2",
        "django-cors-headers>=4.3.0",
        "PyJWT>=2.8.0",
        "bleach>=6.1.0",
        "openpyxl>=3.1.2",
        "psutil>=5.9.0",
        "pyotp>=2.9.0",
        "qrcode>=7.4.2",
        "PyYAML>=6.0.1",
        "requests>=2.32.4",
        "sentry-sdk>=2.8.0",
        "pillow>=10.3.0",
    ],
    extras_require={
        "subscriptions": [
            "channels>=4.0.0",
            "channels-graphql-ws>=0.9.0",
            "daphne>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "rail-admin=rail_django.bin.rail_admin:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 5.0",
        "Framework :: Django :: 5.1",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.11",
)
