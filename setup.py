import os
from setuptools import setup, find_packages

setup(
    name="rail-django",
    version="0.1.0",
    description="A Django wrapper framework with pre-configured settings and tools.",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/rail-django",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Django>=4.2.27",
        "graphene-django>=3.1.5",
        "django-filter>=23.2",
        "django-cors-headers>=4.3.0",
        "PyJWT>=2.8.0",
        "bleach>=6.1.0",
        "requests>=2.32.4",
        "sentry-sdk>=2.8.0",
        "pillow>=10.3.0",
    ],
    entry_points={
        "console_scripts": [
            "rail-admin=rail_django.bin.rail_admin:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 4.2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
)
