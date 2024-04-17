Copy your existing ipv4 isc-dhcpd.conf files to reservations in a postgresql isc-kea database. 

--debug: Enable debugging output.
--dry-run: Perform a dry run without modifying the database, prints what will be entered to the database to stdout.
--file-path: Path to the DHCP leases file.
--no-ip-client-class: Client class to use for reservations without an IP (optional, reservations must reserve either an IP or a class)
--default-subnet-id: Default subnet ID to use when none is found or provided by --subnet-map
--subnet-map: Add subnet mapping in the format prefix=subnet_id e.g., 192.168.0=3. to enter multiple subnets just repeast the flag, ie --subnet-map 192.168.0=3 --subnet-map 192.168.1=2
