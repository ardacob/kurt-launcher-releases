import base64
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import Launcher, LauncherError, Store, Task, atomic_json
from invites import PlayitManager, RelayError, decode_invite, encode_invite, split_endpoint


class InvitationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.launcher = Launcher(self.store)
        self.relay = PlayitManager(self.launcher)
        self.server = {"id": "a"*32, "name": "Friends", "version": "1.20.1", "loader": "fabric",
                       "loader_version": "0.20.1", "port": 25565}

    def test_invite_roundtrip_carries_no_admin_secret(self):
        code = encode_invite("friends.joinmc.link:31245", self.server)
        data = decode_invite(code)
        self.assertEqual(data, {"address": "friends.joinmc.link:31245", "version": "1.20.1", "loader": "fabric", "loader_version": "0.20.1"})
        self.assertNotIn("secret", json.dumps(data))
        self.assertNotIn("agent", json.dumps(data))

    def test_modified_truncated_and_oversized_codes_rejected(self):
        code = encode_invite("friends.ply.gg:30000", self.server)
        for bad in (code[:-4], code[:10]+"A"+code[11:], "other-1234", "KURT1-"+"A"*2000):
            with self.subTest(code=bad[:30]), self.assertRaises(LauncherError): decode_invite(bad)

    def test_private_hosts_and_non_relay_domains_rejected(self):
        for address in ("127.0.0.1:25565", "192.168.1.10:25565", "localhost", "evil.example:80", "foo.ply.gg.evil.example:1",
                        "https://friends.ply.gg", "friends.ply.gg:0", "friends.ply.gg:65536", "friends.ply.gg:25565/extra"):
            with self.subTest(address=address), self.assertRaises(LauncherError): split_endpoint(address)

    def test_valid_checksum_does_not_allow_path_or_type_injection(self):
        payloads = [["friends.ply.gg",25565,"../escape","fabric",None],
                    ["friends.ply.gg",True,"1.20.1","vanilla",None],
                    ["friends.ply.gg",25565,"1.20.1","unknown",None]]
        for payload in payloads:
            raw = json.dumps(payload).encode()
            code = "KURT1-"+base64.urlsafe_b64encode(raw+struct.pack(">I",zlib.crc32(raw))).decode().rstrip("=")
            with self.assertRaises(LauncherError): decode_invite(code)

    def test_cloud_rejects_all_billing_endpoints_before_network(self):
        with patch.object(self.relay.session, "post") as post:
            for path in ("/billing/subscribe", "/charges/create", "/tunnels/upgrade", "https://other.example"):
                with self.assertRaises(RelayError): self.relay.cloud(path,{})
        post.assert_not_called()

    def test_only_same_agent_loopback_minecraft_tunnel_is_reused(self):
        valid = {"tunnel_type":"minecraft-java", "port_type":"tcp", "origin":{"type":"agent","data":{
            "agent_id":"mine","local_ip":"127.0.0.1","local_port":25565}}}
        self.assertIs(self.relay.matching_tunnel([valid],"mine",25565),valid)
        self.assertIsNone(self.relay.matching_tunnel([valid],"other",25565))
        self.assertIsNone(self.relay.matching_tunnel([valid],"mine",25566))
        self.assertIsNone(self.relay.matching_tunnel([{**valid,"tunnel_type":"https"}],"mine",25565))

    def test_publish_requests_only_free_global_minecraft_tunnel(self):
        calls = []
        tunnel = {"tunnel_type":"minecraft-java", "port_type":"tcp", "origin":{"type":"agent","data":{
            "agent_id":"mine","local_ip":"127.0.0.1","local_port":25565}},
            "alloc":{"status":"allocated","data":{"assigned_domain":"friends.joinmc.link","port_start":31245}}}
        def cloud(path,payload,secret=None):
            calls.append((path,payload))
            if path=="/tunnels/create": return {"id":"id"}
            return {"tunnels":[tunnel] if len(calls)>1 else [],"tcp_alloc":{"allowed":1,"claimed":0}}
        state = {"state":"running","data":{"agent_id":"mine","tunnels":[{"destination":"127.0.0.1:25565","is_disabled":False}]}}
        with patch.object(self.relay,"start_agent"), patch.object(self.relay,"secret",return_value="test-key"), \
                patch.object(self.relay,"cloud",side_effect=cloud), patch.object(self.relay,"ipc",return_value=state):
            code = self.relay.publish(self.server,Task())
        request = next(payload for path,payload in calls if path=="/tunnels/create")
        self.assertEqual(request["tunnel_type"],"minecraft-java")
        self.assertEqual(request["alloc"],{"type":"region","details":{"region":"global"}})
        self.assertEqual(request["port_count"],1)
        self.assertIsNone(request["proxy_protocol"])
        self.assertEqual(decode_invite(code)["address"],"friends.joinmc.link:31245")
        self.assertEqual(self.relay.sharing_server_id,self.server["id"])

    def test_free_quota_full_never_creates_or_upgrades(self):
        with patch.object(self.relay,"start_agent"), patch.object(self.relay,"secret",return_value="test-key"), \
                patch.object(self.relay,"ipc",return_value={"state":"running","data":{"agent_id":"mine"}}), \
                patch.object(self.relay,"cloud",return_value={"tunnels":[],"tcp_alloc":{"allowed":1,"claimed":1}}) as cloud:
            with self.assertRaises(RelayError): self.relay.publish(self.server,Task())
        self.assertEqual([call.args[0] for call in cloud.call_args_list],["/tunnels/list"])
        self.assertIsNone(self.relay.address)

    def test_join_selects_matching_profile_and_pins_fabric(self):
        self.store.settings["offline_username"]="Player_1"
        code=encode_invite("friends.ply.gg:30000",self.server)
        with patch.object(self.launcher,"versions",return_value=({"versions":[{"id":"1.20.1"}]},False)), \
                patch("core.mc.mod_loader.get_mod_loader") as get_loader, patch.object(self.launcher,"play",return_value="started") as play:
            get_loader.return_value.get_loader_versions.return_value=["0.20.1"]
            message, pid=self.launcher.join_invite(code,Task())
            self.launcher.join_invite(code,Task())
        self.assertEqual(len(self.store.profiles),1)
        self.assertEqual(self.store.profiles[0]["loader_version"],"0.20.1")
        self.assertEqual(play.call_args.kwargs["join_address"],"friends.ply.gg:30000")
        self.assertEqual(self.store.profiles[0]["id"],pid)

    def test_invited_version_must_exist_in_official_manifest(self):
        self.store.settings["offline_username"]="Player_1"
        code=encode_invite("friends.ply.gg:30000",self.server)
        with patch.object(self.launcher,"versions",return_value=({"versions":[]},False)), patch.object(self.launcher,"play") as play:
            with self.assertRaises(LauncherError): self.launcher.join_invite(code,Task())
        play.assert_not_called()
        self.assertFalse(self.store.profiles)

    def test_quickplay_connects_modern_client_without_legacy_server_flags(self):
        self.store.settings.update(login_mode="offline",offline_username="Player_1")
        profile=self.store.create("Client","1.20.1","vanilla")
        profile["installed"]="1.20.1"
        directory=self.store.minecraft/"versions/1.20.1"
        directory.mkdir(parents=True)
        (directory/"1.20.1.jar").write_bytes(b"fixture")
        atomic_json(directory/"1.20.1.json",{"arguments":{"game":["${quickPlayMultiplayer}"]}})
        with patch.object(self.launcher,"java",return_value="java.exe"), \
                patch("core.mc.command.get_minecraft_command",return_value=["java.exe"]) as command, patch("core.subprocess.Popen"):
            self.launcher.play(profile,Task(),join_address="friends.ply.gg:30000")
        options=command.call_args.args[2]
        self.assertEqual(options["quickPlayMultiplayer"],"friends.ply.gg:30000")
        self.assertNotIn("server",options)

    def test_existing_waiting_helper_restores_key_from_windows_vault(self):
        from types import SimpleNamespace
        self.relay.process = SimpleNamespace(poll=lambda: None)
        with patch.object(self.relay,"secret",return_value="stored-key"), \
                patch.object(self.relay,"ipc",side_effect=[{"has_secret":False},{"accepted":True}]) as ipc:
            self.relay.start_agent(Task())
        self.assertEqual(ipc.call_args_list[1].args,("set_secret",))
        self.assertEqual(ipc.call_args_list[1].kwargs,{"secret":"stored-key"})

    def test_existing_live_tunnel_needs_no_cloud_resource_permissions(self):
        state={"state":"running","data":{"agent_id":"mine","tunnels":[{
            "destination":"127.0.0.1:25565","display_address":"friends.joinmc.link:30123","is_disabled":False}]}}
        with patch.object(self.relay,"start_agent"), patch.object(self.relay,"secret",return_value="stored-key"), \
                patch.object(self.relay,"ipc",return_value=state), patch.object(self.relay,"cloud") as cloud:
            result=self.relay.publish(self.server,Task())
        cloud.assert_not_called()
        self.assertEqual(decode_invite(result)["address"],"friends.joinmc.link:30123")


if __name__=="__main__": unittest.main()
