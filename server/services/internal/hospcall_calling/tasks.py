"""Reserved for service-internal Celery tasks.

Public task entry points live in `calling/tasks.py`. Add internal helper
tasks here when needed (e.g. retry hooks, periodic clean-ups specific to the
service). Empty for now so `mochii/celery.py` autodiscover doesn't no-op
silently if a task lands later.
"""
