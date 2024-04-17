import re
import psycopg2
from psycopg2 import sql, errors
import argparse
import socket
import struct
import binascii

# Database connection parameters
DB_HOST = 'postgresql.host.fqdn'
DB_USER = 'username'
DB_PASS = 'password'
DB_NAME = 'database'


def ip_to_int(ip):
    """Convert a dotted-decimal IP address to an integer."""
    return struct.unpack("!I", socket.inet_aton(ip))[0] if ip else 0


def subnet_lookup(ip_address, subnet_map):
    """Determine the subnet ID based on IP address using a provided subnet map."""
    if ip_address:
        for prefix, subnet_id in subnet_map.items():
            if ip_address.startswith(prefix):
                return subnet_id, None
    return None, None


def mac_to_bytea(mac):
    """Convert a MAC address string to a binary format for PostgreSQL bytea field, ensuring proper octet formatting."""
    # Split the MAC address into parts based on colons.
    parts = mac.split(':')

    # Pad each part with a leading zero if it's only one digit, then reconstruct the MAC address.
    padded_parts = [part.zfill(2) for part in parts]
    formatted_mac = ''.join(padded_parts)  # Join all parts into a single string without colons.
    # Convert the formatted hexadecimal string to a binary (byte) sequence.
    try:
        return binascii.unhexlify(formatted_mac)
    except binascii.Error as e:
        print(f"Error converting MAC address to binary: {e}")
        raise

def parse_subnet_mappings(subnet_strings):
    """Parse subnet mappings from command line arguments."""
    subnet_map = {}
    for s in subnet_strings:
        parts = s.split('=')
        if len(parts) == 2:
            subnet_map[parts[0]] = int(parts[1])
    return subnet_map


def parse_dhcp_leases(file_path, no_ip_client_class, default_subnet_id, subnet_map):
    leases = []
    with open(file_path, 'r') as file:
        content = file.read()

    lease_pattern = re.compile(r'host (\S+) \{\s*hardware ethernet (.*?);(?:\s*fixed-address (.*?);)?\s*\}', re.S)
    matches = lease_pattern.findall(content)

    for match in matches:
        hostname, hwaddr, fixed_address = match
        dhcp4_subnet_id, dhcp6_subnet_id = subnet_lookup(fixed_address, subnet_map)
        if dhcp4_subnet_id is None:
            dhcp4_subnet_id = default_subnet_id  # Use the default subnet ID if None

        ipv4_int_address = ip_to_int(fixed_address) if fixed_address else 0

        lease = {
            'dhcp_identifier': hwaddr,
            'dhcp_identifier_type': 0,
            'dhcp4_subnet_id': dhcp4_subnet_id,
            'dhcp6_subnet_id': dhcp6_subnet_id,
            'ipv4_address': ipv4_int_address,
            'hostname': hostname,
            'dhcp4_client_classes': None if fixed_address else no_ip_client_class,
            'dhcp6_client_classes': '',
            'dhcp4_next_server': 0,
            'dhcp4_server_hostname': '',
            'dhcp4_boot_file_name': '',
            'user_context': '',
            'auth_key': ''
        }
        leases.append(lease)

    return leases

def insert_leases_to_db(leases, dry_run=False, debug=False):
    conn = None
    cursor = None
    try:
        if dry_run:
            for lease in leases:
                lease['dhcp_identifier'] = mac_to_bytea(lease['dhcp_identifier'])
                print("DRY RUN - Would insert:", lease)
            return  # Exit the function after dry run output

        conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, dbname=DB_NAME)
        cursor = conn.cursor()

        insert_query = sql.SQL("""
        INSERT INTO hosts (dhcp_identifier, dhcp_identifier_type, dhcp4_subnet_id, dhcp6_subnet_id, ipv4_address, hostname,
                            dhcp4_client_classes, dhcp6_client_classes, dhcp4_next_server, dhcp4_server_hostname, dhcp4_boot_file_name,
                            user_context, auth_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """)

        for lease in leases:
            if debug:
                print("Error occured at the following lease:", lease)  # Debug output
            lease['dhcp_identifier'] = mac_to_bytea(lease['dhcp_identifier'])  # Convert MAC address to binary before insertion
            cursor.execute(insert_query, (
                lease['dhcp_identifier'],
                lease['dhcp_identifier_type'],
                lease['dhcp4_subnet_id'],
                lease['dhcp6_subnet_id'],
                lease['ipv4_address'],
                lease['hostname'],
                lease['dhcp4_client_classes'],
                lease['dhcp6_client_classes'],
                lease['dhcp4_next_server'],
                lease['dhcp4_server_hostname'],
                lease['dhcp4_boot_file_name'],
                lease['user_context'],
                lease['auth_key']
            ))
        conn.commit()

    except Exception as e:
        print(f"An error occurred: {e}")
        if conn:
            conn.rollback()

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def main():
    parser = argparse.ArgumentParser(description='Process DHCP leases and optionally perform a dry run.')
    parser.add_argument('--debug', action='store_true', help='Enable debugging output.')
    parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without modifying the database.')
    parser.add_argument('--file-path', type=str, default='path_to_your_leases_file',
                        help='Path to the DHCP leases file.')
    parser.add_argument('--no-ip-client-class', type=str, default='no-ip-reservations',
                        help='Client class to use for reservations without an IP.')
    parser.add_argument('--default-subnet-id', type=int, default=0, help='Default subnet ID to use when none is found.')
    parser.add_argument('--subnet-map', action='append',
                        help='Add subnet mapping in the format prefix=subnet_id e.g., 192.168.0=3. to enter multiple subnets just repeast the flag, ie --subnet-map 192.168.0=3 --subnet-map 192.168.1=2')
    args = parser.parse_args()

    subnet_map = parse_subnet_mappings(args.subnet_map if args.subnet_map else [])

    leases = parse_dhcp_leases(args.file_path, args.no_ip_client_class, args.default_subnet_id, subnet_map)
    insert_leases_to_db(leases, dry_run=args.dry_run, debug=args.debug)


if __name__ == '__main__':
    main()
