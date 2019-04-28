from distutils.core import setup
import iview.config
setup(
    name='iview',
    version=iview.config.version,
    packages=['iview'],
    scripts=['iview-cli', 'iview-gtk', 'iview-ng.py'],
    data_files=[('/usr/share/applications', ['iview-gtk.desktop'])],
    install_requires=["PySocks"]
    )
