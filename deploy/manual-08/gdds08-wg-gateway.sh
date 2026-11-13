#!/bin/sh
# Add only the missing B gateway mapping; leave the existing 8443/9443 rules alone.
set -eu
for pair in 'wg-dom 10.78.0.3' 'wg-dom2 10.79.0.3'; do
    set -- $pair
    iptables -w -t nat -C PREROUTING -i "$1" -d "$2" -p tcp --dport 10443 -m comment --comment gdds08-wg-gateway -j DNAT --to-destination 192.168.233.209:10443 2>/dev/null || \
        iptables -w -t nat -A PREROUTING -i "$1" -d "$2" -p tcp --dport 10443 -m comment --comment gdds08-wg-gateway -j DNAT --to-destination 192.168.233.209:10443
    iptables -w -C FORWARD -i "$1" -d 192.168.233.209 -p tcp --dport 10443 -m comment --comment gdds08-wg-gateway -j ACCEPT 2>/dev/null || \
        iptables -w -A FORWARD -i "$1" -d 192.168.233.209 -p tcp --dport 10443 -m comment --comment gdds08-wg-gateway -j ACCEPT
done
iptables -w -t nat -C POSTROUTING -d 192.168.233.209 -p tcp --dport 10443 -m comment --comment gdds08-wg-gateway -j MASQUERADE 2>/dev/null || \
    iptables -w -t nat -A POSTROUTING -d 192.168.233.209 -p tcp --dport 10443 -m comment --comment gdds08-wg-gateway -j MASQUERADE
