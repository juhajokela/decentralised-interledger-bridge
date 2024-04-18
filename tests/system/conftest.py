import pytest


def pytest_addoption(parser):
    parser.addoption("--config_file", action="append", default=[])
    parser.addoption("--transfers", action="store", type=int, default=1)


def pytest_generate_tests(metafunc):
    config_files = metafunc.config.option.config_file
    transfers = metafunc.config.option.transfers

    print('metafunc.fixturenames:', metafunc.fixturenames)

    if 'config_files' in metafunc.fixturenames and config_files is not None:
        metafunc.parametrize("config_files", [config_files])

    if 'config_file' in metafunc.fixturenames and config_files is not None:
        metafunc.parametrize("config_file", [config_files[0]])

    if 'transfers' in metafunc.fixturenames and transfers is not None:
        metafunc.parametrize("transfers", [transfers])
