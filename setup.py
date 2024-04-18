from setuptools import setup, find_packages

setup(
    name='iot-ngin-interledger',
    version='0.1',
    description=(
        'Template implementation of the IoT-NGIN project\'s '
        'Interledger component'
    ),
    url='https://gitlab.com/h2020-iot-ngin/enhancing_iot_cybersecurity_and_data_privacy/fib-interledger/',
    author='IoT-NGIN Project',
    license='APL 2.0',
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    install_requires=[
        'web3 == 5.28.0',
        'cryptography',
        'requests == 2.20.0',
        'protobuf < 4',
        'fabric-sdk-py',
        'asyncio',
        'eth-hash < 0.4.0',
        'eth-rlp == 0.2.1',
        'python3-indy'
    ],
	dependency_links=[
        'https://github.com/hyperledger/fabric-sdk-py/tarball/master#egg=fabric-sdk-py'
    ],
    tests_require=['pytest', 'pytest-asyncio', 'fabric-sdk-py'],
    zip_safe=False
)
