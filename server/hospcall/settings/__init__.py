import logging
import os
from enum import StrEnum
from pathlib import Path


class Env(StrEnum):
    LOCAL = 'local'
    TEST = 'test'
    PROD = 'prod'


ENV = os.environ.get('ENV', Env.LOCAL)
IS_DEPLOYED: bool = os.environ.get('IS_DEPLOYED', 'false').lower() == 'true'

if ENV not in Env:
    raise ValueError(f"Unknown ENV='{ENV}'. Must be one of: {list(Env)}")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if ENV in (Env.LOCAL, Env.TEST):
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / '.local-setup' / f'.env.{ENV}')

    # Personal override (gitignored): .env.local.local
    _local_override = _PROJECT_ROOT / '.local-setup' / f'.env.{ENV}.local'
    if _local_override.exists():
        load_dotenv(_local_override, override=True)

    # Secrets file (gitignored): .env.local.secrets
    _local_secrets = _PROJECT_ROOT / '.local-setup' / f'.env.{ENV}.secrets'
    if _local_secrets.exists():
        load_dotenv(_local_secrets, override=True)
else:
    from services.external.ssm.manager import SSM_HOSPCALL_ENV_PATH, AWSEnvManager

    REGION_NAME = os.environ.get('AWS_REGION', 'us-west-2')
    try:
        AWSEnvManager(region_name=REGION_NAME).fetch_parameter_and_set_envs(
            SSM_HOSPCALL_ENV_PATH
        )
    except Exception as e:
        logging.error('Failed to fetch parameters from AWS SSM: %s', e)
        raise RuntimeError(
            f"Cannot start server: SSM parameter load failed ({e})"
        ) from e

    if not IS_DEPLOYED:
        from dotenv import load_dotenv

        _local_override = _PROJECT_ROOT / '.local-setup' / '.env.prod.local'
        if _local_override.exists():
            load_dotenv(_local_override, override=True)

from hospcall.settings.base import *  # noqa: E402, F403
