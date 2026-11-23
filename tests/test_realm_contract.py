#!/usr/bin/env python3
# Copyright (C) 2026 YIQISOFT
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).parents[1]
CHART = ROOT / "deploy" / "helm" / "nereididentity"


class RealmImportContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rendered = subprocess.run(
            [
                "helm",
                "template",
                "nereididentity",
                str(CHART),
                "--namespace",
                "nereididentity",
                "--values",
                str(CHART / "values-k3s-example.yaml"),
                "--show-only",
                "templates/realm-secret.yaml",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        lines = rendered.splitlines()
        start = lines.index("  nereidai-realm.json: |") + 1
        end = next(
            index
            for index in range(start, len(lines))
            if lines[index].startswith("  admin-client-secret:")
        )
        cls.chart_realm = json.loads(
            "\n".join(line[4:] for line in lines[start:end])
        )
        cls.static_realm = json.loads(
            (ROOT / "realm" / "nereidai-realm.json").read_text(encoding="utf-8")
        )

    def assert_builtin_scope_contract(self, realm):
        # Keycloak 26.1 seeds built-in scopes only when this key is absent.
        self.assertNotIn("clientScopes", realm)
        for client in realm.get("clients", []):
            with self.subTest(client=client.get("clientId")):
                self.assertNotIn("groups", client.get("defaultClientScopes", []))
                self.assertNotIn("groups", client.get("optionalClientScopes", []))

    def test_chart_import_leaves_builtin_scope_creation_to_keycloak(self):
        self.assert_builtin_scope_contract(self.chart_realm)

    def test_static_import_obeys_the_same_contract(self):
        self.assert_builtin_scope_contract(self.static_realm)

    def test_chart_clients_retain_their_builtin_oidc_scopes(self):
        clients = {
            client["clientId"]: client
            for client in self.chart_realm.get("clients", [])
        }
        for client_id in ("nereidsphere", "nereidlink", "nereidhorizon", "nereidforge"):
            with self.subTest(client=client_id):
                self.assertEqual(
                    clients[client_id]["defaultClientScopes"],
                    ["web-origins", "roles", "profile", "email"],
                )
        self.assertEqual(clients["nereidsphere-admin"]["defaultClientScopes"], ["roles"])


if __name__ == "__main__":
    unittest.main()
