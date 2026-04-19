import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

TIERS = {
    "free": {
        "speed_mbit": 5,
        "allow_all": False,
        "allowed_ips": ["140.82.121.3"], # Example IPs, can be adjusted
        "description": "Free tier with 5 Mbps and limited access"
    },
    "basic": {
        "speed_mbit": 20,
        "allow_all": True,
        "allowed_ips": [],
        "description": "Basic tier with 20 Mbps and full internet access"
    },
    "premium": {
        "speed_mbit": 0, # Unrestricted
        "allow_all": True,
        "allowed_ips": [],
        "description": "Premium tier with unlimited speed and full internet access"
    }
}

class TierManager:
    def __init__(self, ssh_manager, container: str, interface: str):
        self.ssh = ssh_manager
        self.container = container
        self.interface = interface

    def _run_cmd(self, cmd: str) -> tuple[str, str]:
        """Helper to run a command inside the container."""
        # Escape single quotes in cmd
        cmd_escaped = cmd.replace("'", "'\\''")
        docker_cmd = f"docker exec -i {self.container} bash -c '{cmd_escaped}'"
        return self.ssh.run_sudo_command(docker_cmd)

    def apply_tier(self, client_ip: str, tier: str) -> None:
        try:
            if tier not in TIERS:
                tier = "free"
            tier_config = TIERS[tier]

            # 1. Clean up old rules
            self.remove_rules(client_ip)

            # 2. Apply iptables rules
            self._apply_iptables(client_ip, tier_config)

            # 3. Apply speed limits
            self._apply_speed_limit(client_ip, tier_config)

        except Exception as e:
            logger.warning(f"Failed to apply tier {tier} for IP {client_ip}: {e}")

    def remove_rules(self, client_ip: str) -> None:
        try:
            # Remove iptables rules
            clean_cmd = f"""
            while iptables -D FORWARD -s {client_ip} -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; do true; done;
            while iptables -D FORWARD -s {client_ip} -p udp --dport 53 -j ACCEPT 2>/dev/null; do true; done;
            while iptables -D FORWARD -s {client_ip} -p tcp --dport 53 -j ACCEPT 2>/dev/null; do true; done;
            while iptables -D FORWARD -s {client_ip} -j DROP 2>/dev/null; do true; done;
            """

            # For allowed_ips, the best way to clean up is to try grep or just loop through all possible allowed_ips of all tiers
            # But the user specifically mentioned deleting everything related to that IP.
            # We'll just remove anything with -s {client_ip} from FORWARD.
            clean_cmd += f"""
            iptables-save | grep "\\-s {client_ip}" | grep "\\-A FORWARD" | sed 's/-A /-D /' | while read rule; do iptables $rule; done
            """
            self._run_cmd(clean_cmd)

            # Remove tc rules
            self._remove_speed_limit(client_ip)
        except Exception as e:
            logger.warning(f"Failed to remove rules for IP {client_ip}: {e}")

    def _apply_iptables(self, client_ip: str, tier_config: Dict[str, Any]) -> None:
        if tier_config["allow_all"]:
            return # No rules needed for full access

        cmds = [
            f"iptables -I FORWARD 1 -s {client_ip} -m state --state ESTABLISHED,RELATED -j ACCEPT",
            f"iptables -I FORWARD 2 -s {client_ip} -p udp --dport 53 -j ACCEPT",
            f"iptables -I FORWARD 3 -s {client_ip} -p tcp --dport 53 -j ACCEPT"
        ]

        index = 4
        for ip in tier_config.get("allowed_ips", []):
            cmds.append(f"iptables -I FORWARD {index} -s {client_ip} -d {ip} -j ACCEPT")
            index += 1

        cmds.append(f"iptables -I FORWARD {index} -s {client_ip} -j DROP")

        full_cmd = "\n".join(cmds)
        self._run_cmd(full_cmd)

    def _apply_speed_limit(self, client_ip: str, tier_config: Dict[str, Any]) -> None:
        speed = tier_config["speed_mbit"]
        if speed <= 0:
            return # No limit

        last_octet = client_ip.split(".")[-1]
        class_id = last_octet

        cmds = [
            # Ensure root qdisc exists (will fail if exists, so we suppress error or just initialize)
            f"tc qdisc add dev {self.interface} root handle 1: htb 2>/dev/null || true",
            f"tc class add dev {self.interface} parent 1: classid 1:1 htb rate 1000mbit 2>/dev/null || true",

            # Add child class for user
            f"tc class replace dev {self.interface} parent 1:1 classid 1:{class_id} htb rate {speed}mbit",
            # Shape download speed by matching destination IP on the wg/awg interface (egress to client)
            f"tc filter add dev {self.interface} protocol ip parent 1:0 prio 1 u32 match ip dst {client_ip}/32 flowid 1:{class_id} 2>/dev/null || true",
            # Replace filter doesn't work correctly without pref/handle, better to just remove and add or use true loop
            f"tc filter replace dev {self.interface} protocol ip parent 1:0 prio 1 u32 match ip dst {client_ip}/32 flowid 1:{class_id}"
        ]

        self._run_cmd("\n".join(cmds))

    def _remove_speed_limit(self, client_ip: str) -> None:
        last_octet = client_ip.split(".")[-1]
        class_id = last_octet

        cmds = [
            f"tc filter del dev {self.interface} protocol ip parent 1:0 u32 match ip dst {client_ip}/32 2>/dev/null || true",
            f"tc filter del dev {self.interface} protocol ip parent 1:0 prio 1 u32 match ip dst {client_ip}/32 2>/dev/null || true",
            f"tc filter del dev {self.interface} protocol ip parent 1:0 prio 1 u32 match ip src {client_ip}/32 2>/dev/null || true",
            f"tc class del dev {self.interface} parent 1:1 classid 1:{class_id} 2>/dev/null || true"
        ]
        self._run_cmd("\n".join(cmds))

    def get_rules_for_ip(self, client_ip: str) -> Dict[str, str]:
        try:
            iptables_stdout, _ = self._run_cmd(f"iptables -S FORWARD | grep {client_ip}")
            tc_stdout, _ = self._run_cmd(f"tc -s class show dev {self.interface} | grep -A 2 -B 2 '1:{client_ip.split('.')[-1]}'")

            return {
                "iptables": iptables_stdout,
                "tc": tc_stdout
            }
        except Exception as e:
            logger.warning(f"Failed to get rules for IP {client_ip}: {e}")
            return {"error": str(e)}

    def apply_all_rules_from_table(self, clients_table: list, tier_map: Dict[str, str]) -> None:
        try:
            for client in clients_table:
                # client typically has 'ip', 'public_key' or 'client_id'
                # Extract client_id from table based on your data structure
                client_id = client.get("client_id")
                if not client_id:
                     continue

                client_ip = client.get("ip")
                if not client_ip:
                     continue

                tier = tier_map.get(client_id, "free")
                self.apply_tier(client_ip, tier)
        except Exception as e:
            logger.warning(f"Failed to apply all rules: {e}")
