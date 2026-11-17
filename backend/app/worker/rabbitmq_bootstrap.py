"""Declare the frozen RetailOps RabbitMQ topology through the management API."""

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


@dataclass(frozen=True)
class BootstrapConfig:
    management_url: str
    admin_user: str
    admin_password: str
    publisher_user: str
    publisher_password: str
    worker_user: str
    worker_password: str
    vhost: str = "/retailops"

    @classmethod
    def from_environment(cls) -> "BootstrapConfig":
        required = (
            "RETAILOPS_RABBITMQ_MANAGEMENT_URL",
            "RABBITMQ_BOOTSTRAP_USER",
            "RABBITMQ_BOOTSTRAP_PASSWORD",
            "RABBITMQ_PUBLISHER_USER",
            "RABBITMQ_PUBLISHER_PASSWORD",
            "RABBITMQ_WORKER_USER",
            "RABBITMQ_WORKER_PASSWORD",
        )
        values = {name: os.environ.get(name) for name in required}
        missing = [name for name, value in values.items() if not value]
        if missing:
            missing_names = ",".join(missing)
            raise RuntimeError(f"Missing RabbitMQ bootstrap variables: {missing_names}")
        return cls(
            management_url=values["RETAILOPS_RABBITMQ_MANAGEMENT_URL"] or "",
            admin_user=values["RABBITMQ_BOOTSTRAP_USER"] or "",
            admin_password=values["RABBITMQ_BOOTSTRAP_PASSWORD"] or "",
            publisher_user=values["RABBITMQ_PUBLISHER_USER"] or "",
            publisher_password=values["RABBITMQ_PUBLISHER_PASSWORD"] or "",
            worker_user=values["RABBITMQ_WORKER_USER"] or "",
            worker_password=values["RABBITMQ_WORKER_PASSWORD"] or "",
        )


class ManagementApi:
    def __init__(self, config: BootstrapConfig) -> None:
        self.config = config
        token = base64.b64encode(
            f"{config.admin_user}:{config.admin_password}".encode()
        ).decode()
        self.authorization = f"Basic {token}"

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.config.management_url.rstrip('/')}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": self.authorization,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"RabbitMQ management request failed: {method} {path} {error.code}"
            ) from error


def bootstrap(config: BootstrapConfig) -> None:
    api = ManagementApi(config)
    vhost = quote(config.vhost, safe="")
    api.request("PUT", f"/api/vhosts/{vhost}", {})
    for username, password in (
        (config.publisher_user, config.publisher_password),
        (config.worker_user, config.worker_password),
    ):
        api.request(
            "PUT",
            f"/api/users/{quote(username, safe='')}",
            {"password": password, "tags": ""},
        )

    api.request(
        "PUT",
        f"/api/permissions/{vhost}/{quote(config.admin_user, safe='')}",
        {"configure": ".*", "write": ".*", "read": ".*"},
    )

    api.request(
        "PUT",
        f"/api/permissions/{vhost}/{quote(config.publisher_user, safe='')}",
        {
            "configure": "^$",
            "write": "^retailops\\.email$",
            "read": "^$",
        },
    )
    api.request(
        "PUT",
        f"/api/permissions/{vhost}/{quote(config.worker_user, safe='')}",
        {
            "configure": "^(retailops\\.email|retailops\\.email\\.v1)$",
            "write": "^retailops\\.email$",
            "read": "^retailops\\.email\\.v1$",
        },
    )
    for exchange in ("retailops.email", "retailops.email.parking"):
        api.request(
            "PUT",
            f"/api/exchanges/{vhost}/{quote(exchange, safe='')}",
            {
                "type": "direct",
                "durable": True,
                "auto_delete": False,
                "internal": False,
                "arguments": {},
            },
        )
    for queue in ("retailops.email.v1", "retailops.email.parked.v1"):
        api.request(
            "PUT",
            f"/api/queues/{vhost}/{quote(queue, safe='')}",
            {
                "durable": True,
                "auto_delete": False,
                "arguments": {"x-queue-type": "quorum"},
            },
        )
    api.request(
        "POST",
        f"/api/bindings/{vhost}/e/retailops.email/q/retailops.email.v1",
        {"routing_key": "email.deliver.v1", "arguments": {}},
    )
    api.request(
        "POST",
        f"/api/bindings/{vhost}/e/retailops.email.parking/q/retailops.email.parked.v1",
        {"routing_key": "email.parked.v1", "arguments": {}},
    )
    api.request(
        "PUT",
        f"/api/policies/{vhost}/retailops-email-live-reliability",
        {
            "pattern": "^retailops\\.email\\.v1$",
            "definition": {
                "dead-letter-exchange": "retailops.email.parking",
                "dead-letter-routing-key": "email.parked.v1",
                "dead-letter-strategy": "at-least-once",
                "overflow": "reject-publish",
                "delivery-limit": 5,
                "max-length-bytes": 67_108_864,
            },
            "priority": 100,
            "apply-to": "quorum_queues",
        },
    )
    queue = api.request("GET", f"/api/queues/{vhost}/retailops.email.v1")
    expected = {
        "dead-letter-exchange": "retailops.email.parking",
        "dead-letter-routing-key": "email.parked.v1",
        "dead-letter-strategy": "at-least-once",
        "overflow": "reject-publish",
        "delivery-limit": 5,
        "max-length-bytes": 67_108_864,
    }
    if (
        queue.get("type") != "quorum"
        or queue.get("effective_policy_definition") != expected
    ):
        raise RuntimeError("RabbitMQ live queue policy is not effective")
    for exchange, queue_name, routing_key in (
        ("retailops.email", "retailops.email.v1", "email.deliver.v1"),
        (
            "retailops.email.parking",
            "retailops.email.parked.v1",
            "email.parked.v1",
        ),
    ):
        bindings = api.request(
            "GET",
            f"/api/bindings/{vhost}/e/{quote(exchange, safe='')}/q/"
            f"{quote(queue_name, safe='')}",
        )
        if not any(binding.get("routing_key") == routing_key for binding in bindings):
            raise RuntimeError(f"RabbitMQ binding is not effective: {exchange}")


if __name__ == "__main__":
    bootstrap(BootstrapConfig.from_environment())
