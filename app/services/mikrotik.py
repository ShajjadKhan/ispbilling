"""
MikroTik RouterOS API Service for PPPoE and Hotspot Subscriber Management.
Uses routeros-api to communicate with MikroTik routers on port 8728 (or 8729 SSL).
Includes full support for:
- PPPoE Secrets & Active Sessions
- Hotspot Users, Profiles & Active Sessions
- IP-Binding & MAC Bypassing (for Android TV, Game Consoles, etc.)
- Auto-discovery from /ip/hotspot/host
- High-level Subscriber Lifecycle Enforcement (Renew, Suspend, Resume, Speed Change)
"""

import logging
from typing import Dict, List, Optional, Any
import routeros_api

logger = logging.getLogger("mikrotik_service")


class MikrotikService:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 8728,
        use_ssl: bool = False,
        plaintext_login: bool = True
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.plaintext_login = plaintext_login
        self._pool: Optional[routeros_api.RouterOsApiPool] = None

    def _get_api(self):
        """Initializes and returns the RouterOS API instance."""
        if self._pool is None:
            self._pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=self.plaintext_login
            )
        return self._pool.get_api()

    def close(self):
        """Disconnects the connection pool cleanly."""
        if self._pool is not None:
            try:
                self._pool.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting RouterOS pool: {e}")
            finally:
                self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # =========================================================================
    # SYSTEM & HEALTH CHECKS
    # =========================================================================
    def test_connection(self) -> Dict[str, Any]:
        """
        Tests router connection and retrieves basic system specifications.
        Returns system identity, RouterOS version, CPU load, uptime, and free RAM.
        """
        api = self._get_api()
        res_resource = api.get_resource("/system/resource")
        res_identity = api.get_resource("/system/identity")

        resource_data = res_resource.get()
        identity_data = res_identity.get()

        res_dict = resource_data[0] if resource_data else {}
        ident_dict = identity_data[0] if identity_data else {}

        return {
            "success": True,
            "identity": ident_dict.get("name", "MikroTik"),
            "version": res_dict.get("version", "Unknown"),
            "cpu_load": res_dict.get("cpu-load", "0"),
            "uptime": res_dict.get("uptime", "0s"),
            "free_memory_mb": round(int(res_dict.get("free-memory", 0)) / (1024 * 1024), 1),
            "total_memory_mb": round(int(res_dict.get("total-memory", 0)) / (1024 * 1024), 1),
            "board_name": res_dict.get("board-name", res_dict.get("platform", "RouterOS")),
        }

    # =========================================================================
    # PPPoE MANAGEMENT (/ppp)
    # =========================================================================
    def get_pppoe_secrets(self) -> List[Dict[str, Any]]:
        """Lists all PPPoE user secrets."""
        api = self._get_api()
        resource = api.get_resource("/ppp/secret")
        return resource.get()

    def get_pppoe_profiles(self) -> List[Dict[str, Any]]:
        """Lists all PPP profiles (speed / rate limit templates)."""
        api = self._get_api()
        resource = api.get_resource("/ppp/profile")
        return resource.get()

    def get_active_pppoe_sessions(self) -> List[Dict[str, Any]]:
        """Lists all currently active / online PPPoE connections."""
        api = self._get_api()
        resource = api.get_resource("/ppp/active")
        return resource.get()

    def add_pppoe_secret(
        self,
        name: str,
        password: str,
        profile: str = "default",
        comment: str = "",
        service: str = "pppoe",
        remote_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new PPPoE secret on RouterOS."""
        api = self._get_api()
        resource = api.get_resource("/ppp/secret")
        params = {
            "name": name,
            "password": password,
            "profile": profile,
            "service": service,
            "comment": comment
        }
        if remote_address:
            params["remote-address"] = remote_address
        return resource.add(**params)

    def update_pppoe_secret(self, name: str, **fields) -> bool:
        """Updates an existing PPPoE secret by username (e.g. disabled='yes', profile=...)."""
        api = self._get_api()
        resource = api.get_resource("/ppp/secret")
        secrets = resource.get(name=name)
        if not secrets:
            raise ValueError(f"PPPoE secret '{name}' not found on router.")
        secret_id = secrets[0]["id"]
        resource.set(id=secret_id, **fields)
        return True

    def delete_pppoe_secret(self, name: str) -> bool:
        """Removes a PPPoE secret from RouterOS."""
        api = self._get_api()
        resource = api.get_resource("/ppp/secret")
        secrets = resource.get(name=name)
        if secrets:
            resource.remove(id=secrets[0]["id"])
            return True
        return False

    def kick_active_pppoe(self, name: str) -> int:
        """
        Terminates active PPPoE session(s) for a subscriber.
        Returns the number of sessions terminated.
        """
        api = self._get_api()
        resource = api.get_resource("/ppp/active")
        active_list = resource.get(name=name)
        kicked = 0
        for act in active_list:
            resource.remove(id=act["id"])
            kicked += 1
        return kicked

    # =========================================================================
    # HOTSPOT MANAGEMENT (/ip/hotspot)
    # =========================================================================
    def get_hotspot_users(self) -> List[Dict[str, Any]]:
        """Lists all Hotspot users."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/user")
        return resource.get()

    def get_hotspot_profiles(self) -> List[Dict[str, Any]]:
        """Lists all Hotspot user profiles."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/user/profile")
        return resource.get()

    def get_active_hotspot_sessions(self) -> List[Dict[str, Any]]:
        """Lists all currently active Hotspot sessions."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/active")
        return resource.get()

    def add_hotspot_user(
        self,
        name: str,
        password: str,
        profile: str = "default",
        comment: str = "",
        mac_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new Hotspot user on RouterOS."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/user")
        params = {
            "name": name,
            "password": password,
            "profile": profile,
            "comment": comment
        }
        if mac_address:
            params["mac-address"] = mac_address
        return resource.add(**params)

    def update_hotspot_user(self, name: str, **fields) -> bool:
        """Updates a Hotspot user by name."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/user")
        users = resource.get(name=name)
        if not users:
            raise ValueError(f"Hotspot user '{name}' not found on router.")
        user_id = users[0]["id"]
        resource.set(id=user_id, **fields)
        return True

    def delete_hotspot_user(self, name: str) -> bool:
        """Deletes a Hotspot user."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/user")
        users = resource.get(name=name)
        if users:
            resource.remove(id=users[0]["id"])
            return True
        return False

    def kick_active_hotspot(self, user: str) -> int:
        """Terminates active Hotspot sessions for a user."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/active")
        active_list = resource.get(user=user)
        kicked = 0
        for act in active_list:
            resource.remove(id=act["id"])
            kicked += 1
        return kicked

    def set_hotspot_profile_shared_users(self, profile_name: str, shared_users: int) -> bool:
        """Sets the shared-users limit on a Hotspot user profile in MikroTik."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/user/profile")
        profiles = resource.get(name=profile_name)
        if profiles:
            resource.set(id=profiles[0]["id"], shared_users=str(shared_users))
            return True
        return False

    # =========================================================================
    # IP-BINDING & MAC BYPASS (For Android TV, Consoles, Non-Browser Devices)
    # =========================================================================
    def get_ip_bindings(self) -> List[Dict[str, Any]]:
        """Lists all Hotspot IP-Bindings (bypassed, blocked, regular)."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/ip-binding")
        return resource.get()

    def add_ip_binding(
        self,
        mac_address: str,
        binding_type: str = "bypassed",
        address: Optional[str] = None,
        comment: str = ""
    ) -> Dict[str, Any]:
        """
        Adds or updates a MAC/IP binding on MikroTik Hotspot idempotently.
        binding_type: 'bypassed' (gives instant internet without login) or 'blocked'.
        """
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/ip-binding")
        clean_mac = mac_address.upper().replace("-", ":").strip()
        for b in resource.get():
            if b.get("mac-address", "").upper() == clean_mac:
                update_params = {"type": binding_type}
                if comment:
                    update_params["comment"] = comment
                if address:
                    update_params["address"] = address
                resource.set(id=b["id"], **update_params)
                return {"id": b["id"], "updated": True}
        params = {
            "mac-address": clean_mac,
            "type": binding_type,
            "comment": comment
        }
        if address:
            params["address"] = address
        return resource.add(**params)

    def update_ip_binding(self, mac_address: str, **fields) -> bool:
        """Updates an existing IP-binding by MAC address."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/ip-binding")
        clean_mac = mac_address.upper().replace("-", ":").strip()
        bindings = resource.get()
        target_id = None
        for b in bindings:
            if b.get("mac-address", "").upper() == clean_mac:
                target_id = b["id"]
                break

        if not target_id:
            raise ValueError(f"IP binding for MAC '{clean_mac}' not found on router.")
        resource.set(id=target_id, **fields)
        return True

    def delete_ip_binding(self, mac_address: str) -> bool:
        """Removes a MAC IP-binding from MikroTik."""
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/ip-binding")
        clean_mac = mac_address.upper().replace("-", ":").strip()
        for b in resource.get():
            if b.get("mac-address", "").upper() == clean_mac:
                resource.remove(id=b["id"])
                return True
        return False

    def get_hotspot_hosts(self) -> List[Dict[str, Any]]:
        """
        Queries /ip/hotspot/host to see all connected devices on the WiFi network.
        Returns IP, MAC, hostname, bypass state, and session statistics.
        Enables 1-click device auto-detection for Android TVs without manual typing.
        """
        api = self._get_api()
        resource = api.get_resource("/ip/hotspot/host")
        hosts = resource.get()
        result = []
        for h in hosts:
            result.append({
                "mac_address": h.get("mac-address"),
                "ip_address": h.get("address"),
                "hostname": h.get("host-name", h.get("comment", "")),
                "bypassed": h.get("bypassed") == "true",
                "authorized": h.get("authorized") == "true",
                "uptime": h.get("uptime", "0s"),
                "bytes_in": h.get("bytes-in", "0"),
                "bytes_out": h.get("bytes-out", "0")
            })
        return result

    # =========================================================================
    # HIGH-LEVEL LIFECYCLE CONTROLLERS (Renew, Suspend, Hold, Resume, Speed)
    # =========================================================================
    def suspend_subscriber(
        self,
        sub_type: str,
        username: str,
        device_macs: Optional[List[str]] = None
    ) -> bool:
        """
        Disables subscriber and kicks online connection immediately.
        Also blocks or removes bypassed MAC bindings (e.g. Android TV).
        """
        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, disabled="yes")
            self.kick_active_pppoe(username)
        else:
            self.update_hotspot_user(username, disabled="yes")
            self.kick_active_hotspot(username)
            if device_macs:
                for mac in device_macs:
                    try:
                        self.update_ip_binding(mac, type="blocked")
                    except Exception as e:
                        logger.warning(f"Could not block MAC {mac}: {e}")
        return True

    def resume_subscriber(
        self,
        sub_type: str,
        username: str,
        profile: Optional[str] = None,
        device_macs: Optional[List[str]] = None
    ) -> bool:
        """
        Re-enables subscriber on MikroTik so they can reconnect.
        Also restores bypassed status for registered devices (e.g. Android TV).
        """
        fields = {"disabled": "no"}
        if profile:
            fields["profile"] = profile

        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, **fields)
        else:
            self.update_hotspot_user(username, **fields)
            if device_macs:
                for mac in device_macs:
                    try:
                        self.update_ip_binding(mac, type="bypassed")
                    except Exception as e:
                        logger.warning(f"Could not restore bypass for MAC {mac}: {e}")
        return True

    def renew_subscriber(
        self,
        sub_type: str,
        username: str,
        expiry_date: str,
        device_macs: Optional[List[str]] = None
    ) -> bool:
        """
        Renews subscriber: ensures enabled=yes, updates expiry date in comment,
        and ensures all devices remain bypassed.
        """
        comment = f"Exp: {expiry_date}"
        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, disabled="no", comment=comment)
        else:
            self.update_hotspot_user(username, disabled="no", comment=comment)
            if device_macs:
                for mac in device_macs:
                    try:
                        self.update_ip_binding(mac, type="bypassed", comment=comment)
                    except Exception as e:
                        logger.warning(f"Could not refresh bypass for MAC {mac}: {e}")
        return True

    def change_subscriber_package(self, sub_type: str, username: str, new_profile: str) -> bool:
        """
        Updates profile speed on router and reconnects session if currently online.
        """
        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, profile=new_profile)
            self.kick_active_pppoe(username)
        else:
            self.update_hotspot_user(username, profile=new_profile)
            self.kick_active_hotspot(username)
        return True
