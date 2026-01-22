# Installation

This guide covers the requirements and installation steps for Rail Django.

## Prerequisites

Rail Django requires the following software:

*   **Python**: 3.11 or higher
*   **Django**: 4.2 or higher
*   **Graphene**: 3.3 or higher

## Installation

You can install `rail-django` directly using pip.

### From PyPI (Recommended)

```bash
pip install rail-django
```

### From Source

If you want the latest development version:

```bash
pip install "rail-django @ git+https://github.com/raillogistic/rail-django.git"
```

## Post-Installation Verification

To verify the installation, you can run the following command in your terminal:

```bash
python -c "import rail_django; print(rail_django.__version__)"
```

If the version number is printed without errors, you are ready to [start your project](quickstart.md).
