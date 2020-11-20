"""NCClient connection funtion"""

from netmiko import ConnectHandler, ssh_exception
from ncclient import manager
import app.Modules.netconfsend as NetconfBase


def creat_netmiko_connection(username, password, host) -> object:
    """Logs into device and returns a connection object to the caller. """

    credentials = {
        'device_type': 'cisco_ios',
        'host': host,
        'username': username,
        'password': password,
        'session_log': 'my_file.out'}

    try:
        device_connect = ConnectHandler(**credentials)
    except ssh_exception.AuthenticationException:
        return "ssh_exception"
    except EOFError:
        return "Authenitcation Error"
    except ssh_exception.NetmikoTimeoutException:
        return 'Connection Timeout'

    return device_connect


def netmiko_w_enable(host: str = None, username: str = None, password: str = None, **enable) -> object:
    """Logs into device and returns a connection object to the caller. """

    try:
        credentials = {
            'device_type': 'cisco_asa',
            'host': host,
            'username': username,
            'password': password,
            'secret': enable["enable_pass"],
            'session_log': 'my_file.out'}

        try:
            device_connect = ConnectHandler(**credentials)
        except ssh_exception.AuthenticationException:
            raise ConnectionError("Could not connect to device {}".format(host))

        return device_connect

    except KeyError:
        pass


def create_netconf_connection(username, password, host) -> manager:
    """Gets current prefix-lists from device and converts from xml to dictionary"""

    try:

        netconf_session = manager.connect(host=host, port=830, username=username,
                                          password=password,
                                          device_params={'name': 'csr'})

    except manager.operations.errors.TimeoutExpiredError as error:
        netconf_session = [error, 'Connection Timeout', 'error']
    except AttributeError as error:
        netconf_session = [error, 'Session Expired', 'error']
    except manager.transport.TransportError as error:
        netconf_session = [error, 'Transport Error', 'error']
    except manager.operations.rpc.RPCError as error:
        netconf_session = [error, 'Configuration Failed', 'error']

    return netconf_session
