import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.export_openwrt import export_package


class PackagingTests(unittest.TestCase):
    def test_procd_passes_log_mode_and_defaults_for_older_uci_config(self):
        template = Path(__file__).resolve().parent.parent / "openwrt/luci-app-iptv-catchup"
        init = (template / "root/etc/init.d/iptv-catchup").read_text(encoding="utf-8")
        harness = r'''
config_load() { :; }
config_get_bool() { eval "$1=1"; }
config_get() {
    local value="${4-}"
    if [ "$3" = access_log ] && [ -n "$mode" ]; then value="$mode"; fi
    eval "$1=\$value"
}
procd_open_instance() { :; }
procd_close_instance() { :; }
procd_set_param() {
    if [ "$1" = command ]; then printf '%s\0' "$@"; fi
}
mode="$1"
'''
        with tempfile.TemporaryDirectory(prefix="iptv-init-test-") as temporary:
            network = Path(temporary) / "network.sh"
            network.write_text('network_get_ipaddr() { eval "$1=192.0.2.1"; }\n'
                               'network_get_device() { eval "$1=br-lan"; }\n', encoding="utf-8")
            self.assertIn(". /lib/functions/network.sh", init)
            script = harness + init.replace(". /lib/functions/network.sh", f'. "{network}"') + "\nstart_service\n"
            for mode, expected in (("", "errors"), ("errors", "errors"), ("all", "all"), ("off", "off")):
                with self.subTest(mode=mode):
                    result = subprocess.run(["sh", "-c", script, "iptv-init-test", mode],
                                            capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    command = result.stdout.decode().split("\0")[:-1]
                    self.assertEqual(command[:4], ["command", "/usr/bin/python3", "-B", "-u"])
                    self.assertEqual(command[-2:], ["--access-log", expected])
                    self.assertEqual(command[command.index("--host") + 1], "192.0.2.1")

    def test_export_includes_deadline_transport_and_standalone_imports(self):
        with tempfile.TemporaryDirectory(prefix="iptv-export-test-") as temporary:
            destination = Path(temporary) / "luci-app-iptv-catchup"
            export_package(destination)
            manifest = json.loads((destination / "SOURCE.json").read_text(encoding="utf-8"))
            self.assertIn("root/usr/lib/iptv-catchup/upstream.py", manifest["sha256"])
            self.assertIn("root/usr/lib/iptv-catchup/diagnostics.py", manifest["sha256"])
            self.assertIn("tests/test_upstream.py", manifest["sha256"])
            self.assertIn("tests/test_diagnostics.py", manifest["sha256"])
            for name, expected in manifest["sha256"].items():
                with self.subTest(file=name):
                    self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), expected)
            runtime = destination / "root/usr/lib/iptv-catchup"
            # Isolate imports from the checkout so missing runtime files cannot hide.
            command = ("import sys; sys.path.insert(0, sys.argv[1]); "
                       "import catchup_server, openwrt_service, upstream, diagnostics")
            result = subprocess.run([sys.executable, "-I", "-B", "-c", command, str(runtime)],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
