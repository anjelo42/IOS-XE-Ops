# -*- encoding: utf-8 -*-

from flask import jsonify, render_template, redirect, request, url_for, flash
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user
)
from app import db, login_manager
from app.base import blueprint
from app.base.forms import LoginForm
import string
from app.base.models import User
from app.base.util import verify_pass
from app.Modules.ProjectRouting.Software import IOSXE
import app.Modules.ProjectRouting.Database.DB_queries as Db_queries
import app.Modules.ProjectRouting.Database.DatabaseOps as DB
import app.Modules.connection as ConnectWith
import app.Modules.GetInterfaces as GetInterfacesInfo
import app.Modules.GetWithNetmiko as GetInfo
import app.Modules.InterfacesQoS as GetQos
import app.Modules.bgp_build as Build_bgp_config
import app.Modules.ospf_build as Build_ospf_config
import app.Modules.netconfsend as SendConfig
import app.Modules.AsrListlist as GetPolicies
import app.Modules.build_service_policy as BuildService
import app.Modules.interface_build as BuildInterface
import sqlite3
import logging
import os

device = None
username = None
password = None
netconf_session = None
netmiko_session = None
get_interfaces = None
local_as = None
service_policies = None
qos = None
model = None
ospf_processes = None
management_int = None
unassigned_ints = None
interface_nums = None

log_dir = os.path.dirname(os.path.realpath(__file__)).replace('base', 'logs\\')
logging.basicConfig(filename=f'{log_dir}sessionlog.log', level=logging.INFO)


@blueprint.route('/')
def route_default():
    return redirect(url_for('base_blueprint.login'))


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    global device, username, password, netconf_session, netmiko_session, model

    login_form = LoginForm(request.form)
    if 'login' in request.form:

        device = request.form['device']
        username = request.form['username']
        password = request.form['password']

        if device and username and password:

            # Attempt to create connection objects. Must have both to get to homepage
            netconf_session = ConnectWith.create_netconf_connection(request.form['username'], request.form['password'],
                                                                    request.form['device'])
            netmiko_session = ConnectWith.creat_netmiko_connection(request.form['username'], request.form['password'],
                                                                   request.form['device'])
            model = GetInfo.get_device_model(netmiko_session)

            # Using netmiko and ncclient for connections, verify that both pass. If one fails, return to login
            if netmiko_session == 'Authenitcation Error':
                flash("Authentication Failure")
                return redirect(url_for('base_blueprint.login'))
            elif netmiko_session == 'ssh_exception' or netmiko_session == 'Connection Timeout':
                flash("Check Device Connectivity")
                return redirect(url_for('base_blueprint.login'))

            if netconf_session == 'Authentication Error':
                flash("Authentication Failure")
                return redirect(url_for('base_blueprint.login'))
            elif netconf_session == 'Connection Timeout' or netconf_session == 'Connectivity Issue':
                flash("Check Device Connectivity")
                return redirect(url_for('base_blueprint.login'))
            else:
                return redirect(url_for('base_blueprint.get_routing'))

        return render_template('accounts/login.html', msg='Wrong user or password', form=login_form)

    if not current_user.is_authenticated:
        return render_template('accounts/login.html',
                               form=login_form)
    return redirect(url_for('home_blueprint.index'))


@blueprint.route('/logout')
def logout():
    """User logout and re-login"""

    logout_user()
    return redirect(url_for('base_blueprint.login'))


@blueprint.route('/routing')
def get_routing():
    """Gets all things routing, arp, interfaces, routing protocols"""

    global get_interfaces, local_as, netconf_session, management_int, unassigned_ints, interface_nums

    netconf_session = ConnectWith.create_netconf_connection(username, password, device)
    get_interfaces = GetInterfacesInfo.get_ip_interfaces(netconf_session, device)
    management_int = get_interfaces[1]
    unassigned_ints = get_interfaces[2]
    interface_nums = get_interfaces[3]
    bgp_status = GetInfo.get_bgp_status(netmiko_session)
    local_as = bgp_status[1][0]
    ospf_status = GetInfo.get_ospf_status(netmiko_session)
    arp_table = GetInfo.get_arp(netmiko_session)

    return render_template('routing.html', interfaces=get_interfaces[0],
                           bgp=bgp_status[0], ospf=ospf_status, arp=arp_table, intial='yes')


@blueprint.route('/routing', methods=['POST'])
def table_refresh():
    """Used for table refreshes"""

    action = request.form.get('action')

    # Used for refreshing tables without page reload, return data to call wich is js/ajax
    if action == 'arp':
        clear = GetInfo.clear_arp(netmiko_session)
        return jsonify({'data': render_template('refresh_arp.html', arps=clear)})
    elif action == 'bgp':
        get_status = GetInfo.get_bgp_status(netmiko_session)
        return jsonify({'data': render_template('refresh_bgp.html', bgp=get_status[0])})
    elif action == 'ospf':
        get_status = GetInfo.get_ospf_status(netmiko_session)
        return jsonify({'data': render_template('refresh_ospf.html', ospf=get_status)})
    elif action == 'clearInt':
        clear = GetInfo.clear_counters(netmiko_session, request.form.get('interface'), netconf_session)
        return jsonify({'data': render_template('refresh_table.html', interfaces=clear)})
    elif action == 'routes':

        # ReAuth and get IOS-XE routing table
        routing_session = ConnectWith.creat_netmiko_connection(username, password, device)
        mydb = sqlite3.connect("app/Modules/ProjectRouting/Database/Routing")
        cursor = mydb.cursor()
        db_obj = DB.RoutingDatabase(mydb, cursor)
        IOSXE.RoutingIos(routing_session, db_obj, mydb, cursor)

        return jsonify({'data': render_template('get_routing.html', route_table=Db_queries.view_routes_ios(cursor))})


@blueprint.route('/qos')
def get_qos():
    """View Qos statistics"""

    global service_policies, qos, netconf_session

    netconf_session = ConnectWith.create_netconf_connection(username, password, device)
    qos = GetQos.get_interfaces(netconf_session)
    service_policies = GetPolicies.fetch_service_policy(netconf_session)

    return render_template('qos.html', interfaces=get_interfaces[0], interface_qos=qos)


@blueprint.route('/modify_qos/<interface>')
def configure_qos(interface):
    """Render QOS configuration/Form"""

    reformat_interface = interface.replace('%2f', '/')

    return render_template('modify_qos.html', interface=reformat_interface, policies=service_policies)


@blueprint.route('/modify_qos', methods=['POST'])
def apply_qos():
    """POST QOS configuration from form data"""

    find_int_num = [i for i in request.form.get("interface") if i not in string.ascii_letters]
    find_int_type = [i for i in request.form.get("interface") if i in string.ascii_letters]
    build_config = BuildService.build_policy(''.join(find_int_type), ''.join(find_int_num),
                                             request.form.get("direction"), request.form.get("servicePolicy"))
    status = SendConfig.send_configuration(netconf_session, build_config)

    if status == 'Success':
        interface_qos = GetQos.get_interfaces(netconf_session)
        return jsonify({'data': render_template('qos_table.html', interface_qos=interface_qos)})
    else:
        return jsonify({'data': render_template('config_failed.html', status=status)})


@blueprint.route('/add_bgp_neighbor')
def add_bgp_neighbors():
    """POST BGP configuration from form data"""

    prefix_lists = GetPolicies.fetch_prefix_list(netconf_session)
    route_maps = GetPolicies.fetch_route_maps(netconf_session)

    if local_as is None:
        return render_template('add_bgp_neighbor.html', local_as="No_AS", prefixes=prefix_lists, route_map=route_maps)
    else:
        return render_template('add_bgp_neighbor.html', local_as=local_as, prefixes=prefix_lists, route_map=route_maps)


@blueprint.route('/add_bgp_neighbor/<neighbor>')
def modify_bgp_neighbors(neighbor):
    """POST BGP configuration from form data"""

    prefix_lists = GetPolicies.fetch_prefix_list(netconf_session)
    route_maps = GetPolicies.fetch_route_maps(netconf_session)

    return render_template('add_bgp_neighbor.html', local_as=local_as, prefixes=prefix_lists, route_map=route_maps,
                           neighbor=neighbor)


@blueprint.route('/add_bgp_neighbor', methods=['POST'])
def post_neighbor():
    """Submit BGP for configuration"""

    build_neighbors = Build_bgp_config.Templates(request.form.get("localAs"))
    bgp_config = build_neighbors.build_neighbor(request.form.get("neighborId"),
                                                request.form.get("remoteAs"),
                                                model,
                                                policy=[request.form.get("softReconfig"),
                                                        request.form.get("direction"),
                                                        request.form.get("policy"),
                                                        request.form.get("nextHop")])
    status = SendConfig.send_configuration(netconf_session, bgp_config)

    if status == 'Success':
        get_status = GetInfo.get_bgp_status(netmiko_session)
        return jsonify({'data': render_template('bgp_neighbor_table.html', bgp=get_status[0])})
    else:
        return jsonify({'data': render_template('config_failed.html', status=status)})


@blueprint.route('/add_ospf_neighbor')
def add_ospf_neighbors():
    """Render OSPF configuration/Form"""

    global ospf_processes

    ospf_processes = GetInfo.get_ospf_processes(netmiko_session)

    return render_template('add_ospf_neighbor.html', ospf_proc=ospf_processes)


@blueprint.route('/add_ospf_neighbor', methods=['POST'])
def post_ospf_neighbor():
    """POST OSPF configuration from form data"""

    build_neighbors = Build_ospf_config.Templates(request.form.get("process"))
    ospf_config = build_neighbors.build_neighbor(request.form.get("neighbor"),
                                                 request.form.get("wildcard"),
                                                 request.form.get("area"))
    status = SendConfig.send_configuration(netconf_session, ospf_config)

    if status == 'Success':
        get_status = GetInfo.get_ospf_status(netmiko_session)
        return jsonify({'data': render_template('ospf_neighbor_table.html', ospf=get_status)})
    else:
        return jsonify({'data': render_template('config_failed.html', status=status)})


@blueprint.route('/new_protocol')
def new_protocol():
    """Add new routing protocol to device"""

    return render_template('new_protocol.html')


@blueprint.route('/new_protocol', methods=['POST'])
def add_new_protocol():
    """Render routing protocol form"""

    if request.form.get('protocol') == 'ospf':
        return render_template('add_ospf_neighbor.html')
    elif request.form.get('protocol') == 'bgp':
        return redirect(url_for('base_blueprint.add_bgp_neighbors'))


@blueprint.route('/modify_inteface/<interface>')
def modify_inteface(interface):
    """POST BGP configuration from form data"""

    reformat_interface = interface.replace('%2f', '/')
    vrfs = GetInfo.get_vrfs(netmiko_session)

    return render_template('modify_interface.html', interface=reformat_interface, vrfs=vrfs, mgmt_int=management_int)


@blueprint.route('/modify_inteface', methods=['POST'])
def submit_inteface():
    """POST interface configuration from form data"""
    global unassigned_ints, interface_nums

    ip = None
    mask = None
    status = None
    descr = None
    vrf = None
    negotiation = None

    int_num = [i for i in request.form.get("interface") if i not in string.ascii_letters]
    int_type = [i for i in request.form.get("interface") if i in string.ascii_letters]
    interface = BuildInterface.Templates(''.join(int_type), ''.join(int_num))

    if request.form.get('ip') and request.form.get('mask'):
        ip = request.form.get('ip')
        mask = request.form.get('mask')
    if request.form.get('status'):
        status = request.form.get('status')
    if request.form.get('description'):
        descr = request.form.get('description')
    if request.form.get('vrf'):
        vrf = request.form.get('vrf')
    if request.form.get('negotiation'):
        negotiation = request.form.get('negotiation')

    config = interface.build_interface(ip, mask, status, descr, vrf, negotiation)
    status = SendConfig.send_configuration(netconf_session, config)

    if status == 'Success':
        show_interfaces = GetInterfacesInfo.get_ip_interfaces(netconf_session)
        unassigned_ints = show_interfaces[2]
        interface_nums = show_interfaces[3]
        return jsonify({'data': render_template('interface_table.html', interfaces=show_interfaces)})
    else:
        return jsonify({'data': render_template('config_failed.html', status=status)})


@blueprint.route('/new_int_form')
def new_interface():
    """POST BGP configuration from form data"""

    vrfs = GetInfo.get_vrfs(netmiko_session)

    return render_template('new_int_form.html', interfaces=unassigned_ints, vrfs=vrfs, interface_numbers=interface_nums)


@blueprint.route('/new_int_form', methods=['POST'])
def submit_new_inteface():
    """POST interface configuration from form data"""

    global unassigned_ints, interface_nums

    ip = None
    mask = None
    status = None
    descr = None
    vrf = None
    negotiation = None

    int_num = [i for i in request.form.get("interface") if i not in string.ascii_letters]
    int_type = [i for i in request.form.get("interface") if i in string.ascii_letters]
    interface = BuildInterface.Templates(''.join(int_type), ''.join(int_num))

    if request.form.get('ip') and request.form.get('mask'):
        ip = request.form.get('ip')
        mask = request.form.get('mask')
    if request.form.get('status'):
        status = request.form.get('status')
    if request.form.get('description'):
        descr = request.form.get('description')
    if request.form.get('vrf'):
        vrf = request.form.get('vrf')
    if request.form.get('negotiation'):
        negotiation = request.form.get('negotiation')

    config = interface.build_interface(ip, mask, status, descr, vrf, negotiation)
    status = SendConfig.send_configuration(netconf_session, config)

    if status == 'Success':
        show_interfaces = GetInterfacesInfo.get_single_interfaces(netconf_session, request.form.get("interface"))
        return jsonify({'data': render_template('new_interface_table.html', interfaces=show_interfaces)})
    else:
        return jsonify({'data': render_template('config_failed.html', status=status)})


@blueprint.route('/about')
def about():
    """Program info"""

    return render_template('about.html')
