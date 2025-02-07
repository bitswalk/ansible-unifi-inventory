#!/usr/bin/env python3

import json
import sys
import requests
import urllib3
from typing import Dict, List
import os
from base64 import b64decode
import argparse

class UnifiInventory:
    def __init__(self):
        # Load configuration from environment variables
        self.controller_host = os.getenv('UNIFI_HOST', 'ctrl.bitswalk.net')
        self.controller_port = os.getenv('UNIFI_PORT', '8443')
        self.site = os.getenv('UNIFI_SITE', 'default')
        self.username = os.getenv('UNIFI_USERNAME')
        self.password = os.getenv('UNIFI_PASSWORD')  # Should be base64 encoded
        self.allow_insecure = os.getenv('UNIFI_ALLOW_INSECURE', '').lower() in ('true', '1', 'yes')

        if not all([self.username, self.password]):
            sys.exit("Missing required environment variables UNIFI_USERNAME or UNIFI_PASSWORD")

        self.base_url = f"https://{self.controller_host}:{self.controller_port}"
        self.session = requests.Session()

        # Configure SSL/TLS verification based on allow_insecure env variable
        if self.allow_insecure:
            # Disable SSL warnings if insecure mode is enabled
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self.session.verify = False
        else:
            # Enable SSL verification
            self.session.verify = True

    def authenticate(self) -> bool:
        """Authenticate with the UniFi Controller"""
        auth_url = f"{self.base_url}/api/login"
        try:
            password = b64decode(self.password).decode('utf-8')
            response = self.session.post(
                auth_url,
                json={"username": self.username, "password": password},
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except Exception as e:
            sys.stderr.write(f"Authentication failed: {str(e)}\n")
            return False

    def get_devices(self) -> List[Dict]:
        """Fetch all devices from the UniFi Controller"""
        devices_url = f"{self.base_url}/api/s/{self.site}/stat/device"
        try:
            response = self.session.get(devices_url)
            if response.status_code == 200:
                return response.json().get('data', [])
            return []
        except Exception as e:
            sys.stderr.write(f"Failed to fetch devices: {str(e)}\n")
            return []

    def get_clients(self) -> List[Dict]:
        """Fetch all active clients"""
        clients_url = f"{self.base_url}/api/s/{self.site}/stat/sta"
        try:
            response = self.session.get(clients_url)
            if response.status_code == 200:
                return response.json().get('data', [])
            return []
        except Exception as e:
            sys.stderr.write(f"Failed to fetch clients: {str(e)}\n")
            return []

    def build_inventory(self) -> Dict:
        """Build the Ansible inventory structure"""
        inventory = {
            '_meta': {
                'hostvars': {}
            },
            'all': {
                'children': ['unifi_devices', 'unifi_clients']
            },
            'unifi_devices': {
                'children': ['switches', 'aps', 'gateways']
            },
            'switches': {'hosts': []},
            'aps': {'hosts': []},
            'gateways': {'hosts': []},
            'unifi_clients': {
                'children': ['wired_clients', 'wireless_clients']
            },
            'wired_clients': {'hosts': []},
            'wireless_clients': {'hosts': []},
        }

        # Process devices
        for device in self.get_devices():
            hostname = device.get('name') or device.get('mac')
            device_type = device.get('type', 'unknown')

            # Add device-specific variables
            inventory['_meta']['hostvars'][hostname] = {
                'mac_address': device.get('mac'),
                'ip_address': device.get('ip'),
                'model': device.get('model'),
                'version': device.get('version'),
                'device_type': device_type,
                'adoption_state': device.get('state', 1),
                'unifi_device': True
            }

            # Categorize devices
            if device_type == 'usw':  # UniFi Switch
                inventory['switches']['hosts'].append(hostname)
            elif device_type == 'uap':  # UniFi Access Point
                inventory['aps']['hosts'].append(hostname)
            elif device_type == 'ugw':  # UniFi Gateway
                inventory['gateways']['hosts'].append(hostname)

        # Process clients
        for client in self.get_clients():
            hostname = client.get('hostname') or client.get('mac')
            is_wired = client.get('is_wired', False)

            # Add client-specific variables
            inventory['_meta']['hostvars'][hostname] = {
                'mac_address': client.get('mac'),
                'ip_address': client.get('ip'),
                'hostname': client.get('hostname'),
                'is_wired': is_wired,
                'last_seen': client.get('last_seen'),
                'unifi_client': True
            }

            # Categorize clients
            if is_wired:
                inventory['wired_clients']['hosts'].append(hostname)
            else:
                inventory['wireless_clients']['hosts'].append(hostname)

        return inventory

    def run(self):
        """Main execution method"""
        if not self.authenticate():
            sys.exit("Authentication failed")

        # Output the inventory in JSON format
        print(json.dumps(self.build_inventory(), indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description='UniFi Ansible Inventory Script')
    parser.add_argument('--list', action='store_true',
                      help='List all inventory hosts (default action)')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    UnifiInventory().run()
