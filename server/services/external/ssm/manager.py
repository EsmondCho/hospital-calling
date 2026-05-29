"""AWS SSM Parameter Store loader.

Pulls every parameter under `SSM_HOSPCALL_ENV_PATH` into `os.environ` at process
start. Mirrors mochii-server's pattern but flattened to a single namespace
since HOSPCALL has only one deployed env (`prod`).
"""

from __future__ import annotations

import os

import boto3
import structlog

logger = structlog.get_logger(__name__)

# Single namespace — no per-env prefix, since HOSPCALL only ever runs one deployed env.
SSM_HOSPCALL_ENV_PATH = '/hospcall'


class AWSEnvManager:
    def __init__(self, *, region_name: str) -> None:
        self.region_name = region_name
        self.client = boto3.client('ssm', region_name=region_name)

    def fetch_parameter_and_set_envs(self, path: str) -> None:
        next_token: str | None = None
        loaded = 0

        while True:
            kwargs = {
                'Path': path,
                'Recursive': True,
                'WithDecryption': True,
                'MaxResults': 10,
            }
            if next_token:
                kwargs['NextToken'] = next_token

            response = self.client.get_parameters_by_path(**kwargs)

            for param in response.get('Parameters', []):
                name = param['Name'].rsplit('/', 1)[-1]
                os.environ[name] = param['Value']
                loaded += 1

            next_token = response.get('NextToken')
            if not next_token:
                break

        logger.info('ssm.params_loaded', path=path, count=loaded)
