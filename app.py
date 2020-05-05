#!/usr/bin/env python3
# slo-reporter
# Copyright(C) 2010 Red Hat, Inc.
#
# This program is free software: you can redistribute it and / or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""This is the main script of Thoth SLO reporter.

    Thanks to DataHub Team in the Red Hat AICoE!!
"""

import os
import logging
import smtplib
import pandas as pd

from typing import Dict

from prometheus_api_client import Metric, MetricsList, PrometheusConnect
from prometheus_api_client.utils import parse_datetime, parse_timedelta
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sli_metrics import SliMetrics


_LOGGER = logging.getLogger("thoth.slo_reporter")

_SERVER = os.environ["SMTP_SERVER"]
_SENDER_ADDRESS = os.environ["SENDER_ADDRESS"]
_ADDRESS_RECIPIENTS = os.environ["EMAIL_RECIPIENTS"]

_THANOS_URL = os.environ["THANOS_ENDPOINT"]
_THANOS_TOKEN = os.environ["THANOS_ACCESS_TOKEN"]
_PUSHGATEWAY_ENDPOINT = os.environ["PROMETHEUS_PUSHGATEWAY_URL"]

PROMETHEUS_REGISTRY = CollectorRegistry()

_THOTH_WEEKLY_SLI = Gauge(
    "thoth_sli_weekly", "Weekly Thoth Service Level Indicators", ["sli_type"], registry=PROMETHEUS_REGISTRY
)

_SLI_REPORT_CONTEXT = {"solved_python_packages": SliMetrics.SOLVED_PYTHON_PACKAGES}


def push_thoth_sli_weekly_metrics(weekly_metrics: Dict[str, Metric], pushgateway_endpoint: str):
    """Push Thoth SLI weekly metric to PushGateway."""
    pushed_metrics = {}
    for sli_type, metric_data in weekly_metrics.items():
        weekly_value_metric = float(metric_data[0]["value"][1])
        _THOTH_WEEKLY_SLI.labels(sli_type=sli_type).set(weekly_value_metric)
        _LOGGER.info("sli_type(%r)=%r", sli_type.message, weekly_value_metric)
        pushed_metrics[sli_type] = weekly_value_metric

    push_to_gateway(pushgateway_endpoint, job="Weekly Thoth SLI", registry=PROMETHEUS_REGISTRY)

    return pushed_metrics


def generate_email(sli_metrics: Dict[str, float]):
    """General email to be sent."""
    message = SliMetrics.INITIAL_MESSAGE
    for metric_name, metric_data in sli_metrics.items():
        report_method = _SLI_REPORT_CONTEXT[metric_name]["report_method"]
        message += "\n" + report_method(metric_data)

    return MIMEText(message, "html")


def send_sli_email(server: str, sender_address: str, recipients: str, weekly_sli_values_map: Dict[str, float]):
    """Send email about Thoth Service Level Objectives."""
    _MAIL_SERVER = smtplib.SMTP(server)

    msg = MIMEMultipart()
    msg["Subject"] = "Thoth Week Service Level Indicators"
    msg["From"] = sender_address
    msg["To"] = recipients

    email_message = generate_email(weekly_sli_values_map)

    msg.attach(email_message)

    _MAIL_SERVER.sendmail(sender_address, recipients, msg.as_string())


def main():
    """Main function for Thoth Service Level Objectives (SLO) Reporter."""
    pc = PrometheusConnect(url=_THANOS_URL, headers={"Authorization": f"bearer {_THANOS_TOKEN}"}, disable_ssl=True)

    collected_info = {}
    for context, data in _SLI_REPORT_CONTEXT.items():
        _LOGGER.info(f"Retrieving data for... {context}")
        collected_info[context] = pc.custom_query(query=SliMetrics[context]["query"])

    weekly_sli_values_map = push_thoth_sli_weekly_metrics(collected_info, _PUSHGATEWAY_ENDPOINT)
    _LOGGER.info(f"Pushed Thoth weekly SLI to Prometheus Pushgateway.")

    send_sli_email(_SERVER, _SENDER_ADDRESS, _ADDRESS_RECIPIENTS, weekly_sli_values_map)
    _LOGGER.info(f"Thoth weekly SLI correctly sent.")


if __name__ == "__main__":
    main()
