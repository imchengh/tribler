import ast
import base64
import logging
import os
from configparser import DuplicateSectionError, MissingSectionHeaderError, NoSectionError, RawConfigParser

from configobj import ConfigObj

import libtorrent as lt

from tribler_common.simpledefs import STATEDIR_CHECKPOINT_DIR

from tribler_core.config.tribler_config import TriblerConfig
from tribler_core.exceptions import InvalidConfigException
from tribler_core.modules.libtorrent.download_config import DownloadConfig
from tribler_core.modules.libtorrent.torrentdef import TorrentDef
from tribler_core.utilities.configparser import CallbackConfigParser
from tribler_core.utilities.unicode import recursive_ungarble_metainfo

logger = logging.getLogger(__name__)


def convert_config_to_tribler71(current_config, state_dir=None):
    """
    Convert the Config files libtribler.conf and tribler.conf to the newer triblerd.conf and cleanup the files
    when we are done.

    :param: current_config: the current config in which we merge the old config files.
    :return: the newly edited TriblerConfig object with the old data inserted.
    """
    state_dir = state_dir or TriblerConfig.get_default_root_state_dir()
    libtribler_file_loc = state_dir / "libtribler.conf"
    if libtribler_file_loc.exists():
        libtribler_cfg = RawConfigParser()
        libtribler_cfg.read(libtribler_file_loc)
        current_config = add_libtribler_config(current_config, libtribler_cfg)
        os.remove(libtribler_file_loc)

    tribler_file_loc = state_dir / "tribler.conf"
    if tribler_file_loc.exists():
        tribler_cfg = RawConfigParser()
        tribler_cfg.read(tribler_file_loc)
        current_config = add_tribler_config(current_config, tribler_cfg)
        os.remove(tribler_file_loc)

    # We also have to update all existing downloads, in particular, rename the section 'downloadconfig' to
    # 'download_defaults'.
    for filename in (state_dir / STATEDIR_CHECKPOINT_DIR).glob('*.state'):
        download_cfg = RawConfigParser()
        try:
            with open(filename) as cfg_file:
                download_cfg.read_file(cfg_file, source=filename)
        except MissingSectionHeaderError:
            logger.error("Removing download state file %s since it appears to be corrupt", filename)
            os.remove(filename)

        try:
            download_items = download_cfg.items("downloadconfig")
            download_cfg.add_section("download_defaults")
            for download_item in download_items:
                download_cfg.set("download_defaults", download_item[0], download_item[1])
            download_cfg.remove_section("downloadconfig")
            with open(filename, "w") as output_config_file:
                download_cfg.write(output_config_file)
        except (NoSectionError, DuplicateSectionError):
            # This item has already been converted
            pass

    return current_config


def add_tribler_config(new_config, old_config):
    """
    Add the old values of the tribler.conf file to the newer Config file.

    :param new_config: The Config file to which the old data can be written
    :param old_config: A RawConfigParser containing the old tribler.conf Config file
    :return: the edited Config file
    """
    config = new_config.copy()
    for section in old_config.sections():
        for (name, string_value) in old_config.items(section):
            if string_value == "None":
                continue

            # Attempt to interpret string_value as a string, number, tuple, list, dict, boolean or None
            try:
                value = ast.literal_eval(string_value)
            except (ValueError, SyntaxError):
                value = string_value

            temp_config = config.copy()
            if section == "Tribler" and name == "default_anonymity_enabled":
                temp_config.set_default_anonymity_enabled(value)
            if section == "Tribler" and name == "default_number_hops":
                temp_config.set_default_number_hops(value)
            if section == "downloadconfig" and name == "saveas":
                temp_config.config["download_defaults"]["saveas"] = value
            if section == "downloadconfig" and name == "seeding_mode":
                temp_config.config["download_defaults"]["seeding_mode"] = value
            if section == "downloadconfig" and name == "seeding_ratio":
                temp_config.config["download_defaults"]["seeding_ratio"] = value
            if section == "downloadconfig" and name == "seeding_time":
                temp_config.config["download_defaults"]["seeding_time"] = value
            if section == "downloadconfig" and name == "version":
                temp_config.config["download_defaults"]["version"] = value

            try:
                temp_config.validate()
                config = temp_config
            except InvalidConfigException as exc:
                logger.debug("The following field in the old tribler.conf was wrong: %s", exc.args)
    return config


def add_libtribler_config(new_config, old_config):
    """
    Add the old values of the libtribler.conf file to the newer Config file.

    :param new_config: the Config file to which the old data can be written
    :param old_config: a RawConfigParser containing the old libtribler.conf Config file
    :return: the edited Config file
    """
    config = new_config.copy()
    for section in old_config.sections():
        for (name, string_value) in old_config.items(section):
            if string_value == "None":
                continue

            # Attempt to interpret string_value as a string, number, tuple, list, dict, boolean or None
            try:
                value = ast.literal_eval(string_value)
            except (ValueError, SyntaxError):
                value = string_value

            temp_config = config.copy()
            if section == "general" and name == "state_dir":
                temp_config.set_root_state_dir(value)
            elif section == "general" and name == "log_dir":
                temp_config.set_log_dir(value)
            elif section == "tunnel_community" and name == "enabled":
                temp_config.set_tunnel_community_enabled(value)
            elif section == "tunnel_community" and name == "socks5_listen_ports":
                if isinstance(value, list):
                    temp_config.set_tunnel_community_socks5_listen_ports(value)
            elif section == "tunnel_community" and name == "exitnode_enabled":
                temp_config.set_tunnel_community_exitnode_enabled(value)
            elif section == "general" and name == "ec_keypair_filename_multichain":
                temp_config.set_trustchain_keypair_filename(value)
            elif section == "torrent_checking" and name == "enabled":
                temp_config.set_torrent_checking_enabled(value)
            elif section == "libtorrent" and name == "lt_proxytype":
                temp_config.config["libtorrent"]["proxy_type"] = value
            elif section == "libtorrent" and name == "lt_proxyserver":
                temp_config.config["libtorrent"]["proxy_server"] = value
            elif section == "libtorrent" and name == "lt_proxyauth":
                temp_config.config["libtorrent"]["proxy_auth"] = value
            elif section == "libtorrent" and name == "max_connections_download":
                temp_config.set_libtorrent_max_conn_download(value)
            elif section == "libtorrent" and name == "max_download_rate":
                temp_config.set_libtorrent_max_download_rate(value)
            elif section == "libtorrent" and name == "max_upload_rate":
                temp_config.set_libtorrent_max_upload_rate(value)
            elif section == "libtorrent" and name == "utp":
                temp_config.set_libtorrent_utp(value)
            elif section == "libtorrent" and name == "anon_listen_port":
                temp_config.set_anon_listen_port(value)
            elif section == "libtorrent" and name == "anon_proxytype":
                temp_config.config["libtorrent"]["anon_proxy_type"] = value
            elif section == "libtorrent" and name == "anon_proxyserver":
                if isinstance(value, tuple) and isinstance(value[1], list):
                    temp_config.config["libtorrent"]["anon_proxy_server_ip"] = value[0]
                    temp_config.config["libtorrent"]["anon_proxy_server_ports"] = [str(port) for port in value[1]]
            elif section == "libtorrent" and name == "anon_proxyauth":
                temp_config.config["libtorrent"]["anon_proxy_auth"] = value
            elif section == "video" and name == "enabled":
                temp_config.set_video_server_enabled(value)
            elif section == "video" and name == "port":
                temp_config.set_video_server_port(value)
            elif section == "watch_folder" and name == "enabled":
                temp_config.set_watch_folder_enabled(value)
            elif section == "watch_folder" and name == "watch_folder_dir":
                temp_config.set_watch_folder_path(value)
            elif section == "http_api" and name == "enabled":
                temp_config.set_http_api_enabled(value)
            elif section == "http_api" and name == "port":
                temp_config.set_http_api_port(value)
            elif section == "credit_mining" and name == "enabled":
                temp_config.set_credit_mining_enabled(value)
            elif section == "credit_mining" and name == "sources":
                temp_config.set_credit_mining_sources(value)

            try:
                temp_config.validate()
                config = temp_config
            except InvalidConfigException as exc:
                logger.debug("The following field in the old libtribler.conf was wrong: %s", exc.args)

    return config


def convert_config_to_tribler74(state_dir=None):
    """
    Convert the download config files to Tribler 7.4 format. The extensions will also be renamed from .state to .conf
    """
    from lib2to3.refactor import RefactoringTool, get_fixers_from_package
    refactoring_tool = RefactoringTool(fixer_names=get_fixers_from_package('lib2to3.fixes'))

    state_dir = state_dir or TriblerConfig.get_default_root_state_dir()
    for filename in (state_dir / STATEDIR_CHECKPOINT_DIR).glob('*.state'):
        old_config = CallbackConfigParser()
        try:
            old_config.read_file(str(filename))
        except MissingSectionHeaderError:
            logger.error("Removing download state file %s since it appears to be corrupt", filename)
            os.remove(str(filename))

        # We first need to fix the .state file such that it has the correct metainfo/resumedata
        for section, option in [('state', 'metainfo'), ('state', 'engineresumedata')]:
            value = old_config.get(section, option, literal_eval=False)
            value = str(refactoring_tool.refactor_string(value+'\n', option + '_2to3'))
            ungarbled_dict = recursive_ungarble_metainfo(ast.literal_eval(value))
            try:
                value = ungarbled_dict or ast.literal_eval(value)
                old_config.set(section, option, base64.b64encode(lt.bencode(value)).decode('utf-8'))
            except (ValueError, SyntaxError):
                logger.error("Removing download state file %s since it could not be converted", filename)
                os.remove(str(filename))
                continue

        # Remove dlstate since the same information is already stored in the resumedata
        if old_config.has_option('state', 'dlstate'):
            old_config.remove_option('state', 'dlstate')

        new_config = ConfigObj(infile=str(filename)[:-6] + '.conf', encoding='utf8')
        for section in old_config.sections():
            for key, _ in old_config.items(section):
                val = old_config.get(section, key)
                if section not in new_config:
                    new_config[section] = {}
                new_config[section][key] = val
        new_config.write()
        os.remove(str(filename))


def convert_config_to_tribler75(state_dir=None):
    """
    Convert the download config files from Tribler 7.4 to 7.5 format.
    """
    state_dir = state_dir or TriblerConfig.get_default_root_state_dir()
    for filename in (state_dir / STATEDIR_CHECKPOINT_DIR).glob('*.conf'):
        config = DownloadConfig.load(filename)
        metainfo = config.get_metainfo()
        if not config.config['download_defaults'].get('selected_files') or not metainfo:
            continue  # no conversion needed/possible, selected files will be reset to their default (i.e., all files)
        tdef = TorrentDef.load_from_dict(metainfo)
        config.set_selected_files([tdef.get_index_of_file_in_files(fn)
                                   for fn in config.config['download_defaults'].pop('selected_files')])
        config.write(str(filename))
