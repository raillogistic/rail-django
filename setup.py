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
        "Django>=4.2.0",
        "graphene>=3.4.0",
        "graphene-django>=3.2.0",
        "django-filter>=24.0.0",
        "graphene-file-upload>=1.3.0",
        "django-cors-headers>=4.0.0",
        "weasyprint==60.1",
        "pillow==10.4.0",
        "PyJWT==2.9.0",
        "bleach==6.1.0",
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
