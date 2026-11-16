"""Build packages with example defaults, never the developer's local conf.py."""

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def find_modules(self):
        return [*super().find_modules(), ("", "conf", "conf.example.py")]


setup(cmdclass={"build_py": BuildPy})
