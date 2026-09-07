"""
MikroTik RouterOS API Service for PPPoE and Hotspot Subscriber Management.
Uses routeros-api to communicate with MikroTik routers on port 8728 (or 8729 SSL).
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

    # =========================================================================
    # HIGH-LEVEL LIFECYCLE CONTROLLERS (Renew, Suspend, Hold, Resume, Speed)
    # =========================================================================
    def suspend_subscriber(self, sub_type: str, username: str) -> bool:
        """
        Disables subscriber and kicks online connection immediately.
        """
        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, disabled="yes")
            self.kick_active_pppoe(username)
        else:
            self.update_hotspot_user(username, disabled="yes")
            self.kick_active_hotspot(username)
        return True

    def resume_subscriber(self, sub_type: str, username: str, profile: Optional[str] = None) -> bool:
        """
        Re-enables subscriber on MikroTik so they can reconnect.
        """
        fields = {"disabled": "no"}
        if profile:
            fields["profile"] = profile

        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, **fields)
        else:
            self.update_hotspot_user(username, **fields)
        return True

    def renew_subscriber(self, sub_type: str, username: str, expiry_date: str) -> bool:
        """
        Renews subscriber: ensures enabled=yes and updates expiry date in comment.
        """
        comment = f"Exp: {expiry_date}"
        if sub_type.lower() == "pppoe":
            self.update_pppoe_secret(username, disabled="no", comment=comment)
        else:
            self.update_hotspot_user(username, disabled="no", comment=comment)
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
