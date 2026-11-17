"""What makes this add-on Apporo's on Home Assistant: its name, slug, image and
repository, with the add-on's interface kept as it was.

The slug and the image decide what Home Assistant installs and pulls. A merge
from the WOOW line that brought back its slug or image would make this add-on
replace or run WOOW's, so these are pinned here. Needs PyYAML.
"""
from pathlib import Path
import re
import unittest

import yaml

ADDON = Path(__file__).resolve().parents[1]
REPO = ADDON.parent

NAME = "Apporo CF Tunnel Web"
DESCRIPTION = ("Connect an Apporo Security Access (Cloudflare Tunnel) to Home Assistant "
               "without opening ports, with a Web GUI")
REPOSITORY_URL = "https://github.com/WOOWTECH/Apporo_ha_cf_tunnel_webgui"

# WOOW's add-on name, repository, image, domains and App Store pipeline.
WOOW_IDENTITY = ("woow cloudflared", "woow_ha_cloudflare_tunnel_webgui",
                 "addon-cloudflared-webgui", "woowtech.io", "woow_ha_app_store",
                 "woow-addon")


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _version(text):
    return tuple(int(part) for part in text.split("."))


def _packaging_files():
    """Files that define the add-on, its image, its runtime and its CI."""
    files = [REPO / "repository.yaml", ADDON / "config.yaml", ADDON / "Dockerfile",
             ADDON / ".dockerignore"]
    for directory in (ADDON / "translations", ADDON / "rootfs", REPO / ".github"):
        files += [path for path in directory.rglob("*") if path.is_file()]
    return sorted(files)


class AddonIdentity(unittest.TestCase):
    def setUp(self):
        self.config = _yaml(ADDON / "config.yaml")

    def test_config_names_the_apporo_addon(self):
        self.assertEqual(self.config["name"], NAME)
        self.assertEqual(self.config["slug"], "apporo_cf_tunnel_web")
        self.assertEqual(self.config["description"], DESCRIPTION)
        self.assertEqual(self.config["url"], REPOSITORY_URL)
        self.assertEqual(self.config["image"], "ghcr.io/woowtech/{arch}-addon-apporo-cf-tunnel-web")
        self.assertEqual(self.config["panel_title"], "Apporo Tunnel")
        self.assertRegex(str(self.config["version"]), r"^\d+\.\d+\.\d+$")

    def test_no_breaking_version_from_another_version_line(self):
        # Upstream's 5.3.7 and 6.0.0 would force manual updates once this line
        # reaches them. Only this line's own past versions belong here.
        current = _version(str(self.config["version"]))
        for breaking in self.config.get("breaking_versions", []):
            self.assertLessEqual(_version(str(breaking)), current, breaking)

    def test_addon_interface_is_unchanged(self):
        expected = {
            "startup": "services", "init": False, "hassio_api": True, "hassio_role": "manager",
            "ingress": True, "ingress_port": 8099, "ingress_panel": True,
            "panel_icon": "mdi:cloud-lock-outline", "arch": ["aarch64", "amd64"],
            "map": ["addon_config:rw", "homeassistant_config"],
            "options": {"external_hostname": "", "additional_hosts": []},
            "ports": {"36500/tcp": None},
        }
        self.assertEqual({key: self.config.get(key) for key in expected}, expected)
        self.assertEqual(set(self.config["schema"]), {
            "external_hostname", "additional_hosts", "tunnel_name", "catch_all_service",
            "nginx_proxy_manager", "tunnel_token", "post_quantum", "run_parameters", "log_level"})
        self.assertEqual(self.config["schema"]["tunnel_token"], "password?")

    def test_repository_is_apporo(self):
        self.assertEqual(_yaml(REPO / "repository.yaml"), {
            "name": "Apporo CF Tunnel Web (Apporo)",
            "url": REPOSITORY_URL,
            "maintainer": "Apporo <info@apporo.ai>",
        })

    def test_image_labels_are_apporo(self):
        dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
        args = dict(re.findall(r'^ARG (BUILD_\w+)="([^"]*)"$', dockerfile, re.MULTILINE))
        # home-assistant/builder does not pass these, so the defaults are the labels.
        self.assertEqual(args.get("BUILD_NAME"), NAME)
        self.assertEqual(args.get("BUILD_DESCRIPTION"), DESCRIPTION)
        self.assertEqual(args.get("BUILD_REPOSITORY"), REPOSITORY_URL.removeprefix("https://github.com/"))
        self.assertIn('maintainer="Apporo <info@apporo.ai>"', dockerfile)
        self.assertIn('org.opencontainers.image.vendor="Apporo"', dockerfile)
        self.assertIn('org.opencontainers.image.authors="Apporo <info@apporo.ai>"', dockerfile)

    def test_translations_cover_every_option_and_port(self):
        schema, ports = set(self.config["schema"]), set(self.config["ports"])
        files = sorted((ADDON / "translations").glob("*.yaml"))
        self.assertIn("en.yaml", [path.name for path in files])
        for path in files:
            with self.subTest(path.name):
                translation = _yaml(path)
                self.assertEqual(set(translation["configuration"]), schema)
                self.assertEqual(set(translation["network"]), ports)
                for key, entry in translation["configuration"].items():
                    self.assertTrue(entry.get("name") and entry.get("description"), key)

    def test_token_help_points_to_the_apporo_link_page(self):
        for name in ("en.yaml", "zh-Hant.yaml"):
            help_text = _yaml(ADDON / "translations" / name)["configuration"]["tunnel_token"]["description"]
            self.assertIn("Apporo Link", help_text, name)

    def test_packaging_never_names_the_woow_addon(self):
        hits = []
        for path in _packaging_files():
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            hits += [f"{path.relative_to(REPO)}: {marker}" for marker in WOOW_IDENTITY if marker in text]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
