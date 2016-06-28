import re
from setuptools import setup, find_packages

# Parse the version from the __init__.py file
version = ''
with open('packsible/__init__.py', 'r') as fd:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                        fd.read(), re.MULTILINE).group(1)

if not version:
    raise RuntimeError('Cannot find version information')

setup(
    name="packsible",
    version=version,
    license="MIT",
    author="Reuven V. Gonzales",
    url="https://github.com/packsible/packsible",
    author_email="reuven@virtru.com",
    description="Combine the power of packer and ansible conveniently",
    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    zip_safe=False,
    platforms='*nix',
    install_requires=[
        "click==6.6",
        "PyYAML==3.11",
        "flask==0.11",
        "GitPython==2.0.5",
    ],
    entry_points={
        'console_scripts': [
            'packsible = packsible.cli:cli',
        ],
    },
    classifiers = [],
)
