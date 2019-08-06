import logging
import os

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache

from box import Box
from tavern.util import exceptions
from tavern.util.dict_util import format_keys
from tavern.util.general import load_global_config

logger = logging.getLogger(__name__)


def add_parser_options(parser_addoption, with_defaults=True):
    """Add argparse options

    This is shared between the CLI and pytest (for now)

    See also testutils.pytesthook.hooks.pytest_addoption
    """
    parser_addoption(
        "--tavern-global-cfg",
        help="One or more global configuration files to include in every test",
        required=False,
        nargs="+",
    )
    parser_addoption(
        "--tavern-http-backend",
        help="Which http backend to use",
        default="requests" if with_defaults else None,
    )
    parser_addoption(
        "--tavern-mqtt-backend",
        help="Which mqtt backend to use",
        default="paho-mqtt" if with_defaults else None,
    )
    parser_addoption(
        "--tavern-strict",
        help="Default response matching strictness",
        default=None,
        nargs="+",
        choices=["body", "headers", "redirect_query_params"],
    )
    parser_addoption(
        "--tavern-beta-new-traceback",
        help="Use new traceback style (beta)",
        default=False,
        action="store_true",
    )
    parser_addoption(
        "--tavern-file-path-regex",
        help="Regex to search for Tavern YAML test files",
        default=r".+\.tavern\.ya?ml$",
        action="store",
        nargs=1,
    )


@lru_cache()
def load_global_cfg(pytest_config):
    """Load globally included config files from cmdline/cfg file arguments

    Args:
        pytest_config (pytest.Config): Pytest config object

    Returns:
        dict: variables/stages/etc from global config files

    Raises:
        exceptions.UnexpectedKeysError: Invalid settings in one or more config
            files detected
    """
    # Load ini first
    ini_global_cfg_paths = pytest_config.getini("tavern-global-cfg") or []
    # THEN load command line, to allow overwriting of values
    cmdline_global_cfg_paths = pytest_config.getoption("tavern_global_cfg") or []

    all_paths = ini_global_cfg_paths + cmdline_global_cfg_paths
    global_cfg = load_global_config(all_paths)

    try:
        loaded_variables = global_cfg["variables"]
    except KeyError:
        logger.debug("Nothing to format in global config files")
    else:
        tavern_box = Box({"tavern": {"env_vars": dict(os.environ)}})

        global_cfg["variables"] = format_keys(loaded_variables, tavern_box)

    strict = get_option_generic(pytest_config, "tavern-strict", [])
    if isinstance(strict, list):
        valid_keys = ["body", "headers", "redirect_query_params"]
        if any(i not in valid_keys for i in strict):
            msg = "Invalid values for 'strict' given - expected one of {}, got {}".format(
                valid_keys, strict
            )
            raise exceptions.InvalidConfigurationException(msg)

    # Can be overridden in tests
    global_cfg["strict"] = strict

    global_cfg["backends"] = {}
    backends = ["http", "mqtt"]
    for b in backends:
        # similar logic to above - use ini, then cmdline if present
        ini_opt = pytest_config.getini("tavern-{}-backend".format(b))
        cli_opt = pytest_config.getoption("tavern_{}_backend".format(b))

        in_use = ini_opt
        if cli_opt and (cli_opt != ini_opt):
            in_use = cli_opt

        global_cfg["backends"][b] = in_use

    logger.debug("Global config: %s", global_cfg)

    return global_cfg


def get_option_generic(pytest_config, flag, default):
    ini_flag = flag.replace("-", "_")
    cli_flag = flag

    if pytest_config.getini(ini_flag) is not None:
        # Lowest priority
        return pytest_config.getini(ini_flag)
    elif pytest_config.getoption(cli_flag) is not None:
        # Middle priority
        return pytest_config.getoption(cli_flag)
    else:
        return default
