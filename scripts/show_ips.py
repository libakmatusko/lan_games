"""Print local IPv4 addresses useful for LAN and VPN clients."""

from lan_games.server.app import local_addresses

if __name__ == "__main__":
    for address in local_addresses():
        print(address)
