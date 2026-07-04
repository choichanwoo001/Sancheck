from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'verso_pkg'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
        (os.path.join('share', package_name, 'scripts'),
            glob('scripts/*.sh')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='verso',
    maintainer_email='todo@todo.com',
    description='Human Guidance (Escort) for Scout Mini',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'person_tracker = verso_pkg.person_tracker_node:main',
            'escort_controller = verso_pkg.escort_controller_node:main',
            'cmd_vel_mux = verso_pkg.cmd_vel_mux_node:main',
            'mission_manager = verso_pkg.mission_manager_node:main',
            'web_bridge = verso_pkg.web_bridge_node:main',
            'guided_escort = verso_pkg.guided_escort_node:main',
        ],
    },
)
