""" Collection of funtions used to send, save, and validate XML responses"""

import lxml.etree as ET
import xml.etree.cElementTree as xml
from ncclient import manager


def prepare_config(config):
    """Prepare config for sending directly from string"""

    xmlstr = xml.tostring(config, method='xml')
    converted_config = xmlstr.decode('utf-8')
    print(converted_config)

    return converted_config


def check_rpc_reply(response):
    """Checks RPC Reply for string. Notifies user config was saved"""

    if response.rfind("Save running-config successful") != -1:
        return 'Configuration Saved'
    elif response.rfind("<ok/>") != -1:
        return 'Success'
    elif response.rfind("<data></data>") != -1:
        return 'Empty Config'


def save_running_config(session):
    """Save new configuration to running config"""

    save_payload = """
                       <cisco-ia:save-config xmlns:cisco-ia="http://cisco.com/yang/cisco-ia"/>
                       """
    try:
        response = session.dispatch(ET.fromstring(save_payload)).xml
        validate_response = check_rpc_reply(response)
    except manager.operations.errors.TimeoutExpiredError as error:
        validate_response = [error, 'Connection Timeout']
    except AttributeError as error:
        validate_response = [error, 'Session Expired']
    except manager.transport.TransportError as error:
        validate_response = [error, 'Transport Error']
    except manager.operations.rpc.RPCError as error:
        validate_response = [error, 'Configuration Failed']

    response = prepare_response(validate_response)

    return response


def prepare_response(send_config):

    if send_config[1] == 'Connection Timeout':
        response = send_config[0]
    elif send_config[1] == 'Session Expired':
        response = send_config[0]
    elif send_config[1] == 'Transport Error':
        response = send_config[0]
    elif send_config[1] == 'Configuration Failed':
        response = send_config[0]
    elif send_config == 'Success':
        response = 'Success'
    else:
        response = 'Configuration Failed'

    return response


def send_configuration(netconf_session, config):
    """Send configuration via NETCONF"""

    formatted_config = prepare_config(config)

    try:
        response = netconf_session.edit_config(formatted_config, target="running")
        validate_response = check_rpc_reply(str(response))
    except manager.operations.errors.TimeoutExpiredError as error:
        validate_response = [error, 'Connection Timeout']
    except AttributeError as error:
        validate_response = [error, 'Session Expired']
    except manager.transport.TransportError as error:
        validate_response = [error, 'Transport Error']
    except manager.operations.rpc.RPCError as error:
        validate_response = [error, 'Configuration Failed']

    response = prepare_response(validate_response)

    return response
