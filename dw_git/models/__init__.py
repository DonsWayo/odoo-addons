# project_link defines git.task.link.mixin, which commit.py and
# pull_request.py inherit. Odoo sets models up in registration order, so
# importing it after them raises "inherits from non-existing model".
# Keep this import first; isort would otherwise fold it into the line below.
from . import project_link  # isort: skip

from . import (
    branch,
    commit,
    deploy_key,
    pat,
    project_task,
    pull_request,
    repository,
    webhook,
)
