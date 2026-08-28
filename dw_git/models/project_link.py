"""Link commits and pull requests to project tasks.

`git.repository.project_id` existed, was filterable, and nothing read it —
the whole `project` dependency was carried to support one dead field. This
is the integration it was there for, and the reason to host Git inside an
ERP at all: a standalone Git host cannot see your tasks.
"""
import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)

#: Task references inside commit messages, PR titles and PR descriptions.
#:
#: Deliberately NOT a bare `#123`. Pull requests are numbered per
#: repository and displayed as `#5`, so a bare number would be read by a
#: human as "pull request 5" and by us as "task 5" — two meanings for one
#: token, in the same sentence. `task-123`, `task #123` and `#task-123` all
#: work, and none of them is ambiguous.
#:
#: A leading keyword marks a reference that should CLOSE the task when the
#: pull request merges, the way GitHub treats "fixes #12".
TASK_REF_RE = re.compile(
    r"""(?:(?P<closing>close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+)?
        \#?task[-\s#]*(?P<task_id>\d+)""",
    re.IGNORECASE | re.VERBOSE,
)


class GitTaskLinkMixin(models.AbstractModel):
    """Shared reference parsing for anything that can mention a task."""
    _name = 'git.task.link.mixin'
    _description = 'Git Task Reference Parsing'

    def _extract_task_refs(self, *texts):
        """Return {task_id: closes} for every task referenced in `texts`.

        `closes` is True when at least one reference carried a closing
        keyword, so "fixes task-12" wins over a bare "task-12" elsewhere in
        the same message.
        """
        found = {}
        for text in texts:
            if not text:
                continue
            # descriptions are HTML; tags would otherwise split a reference
            plain = re.sub(r'<[^>]+>', ' ', str(text))
            for match in TASK_REF_RE.finditer(plain):
                task_id = int(match.group('task_id'))
                closes = bool(match.group('closing'))
                found[task_id] = found.get(task_id, False) or closes
        return found

    def _resolve_tasks(self, task_ids):
        """Tasks the CURRENT user may actually read.

        Referenced through sudo() nowhere: a commit message must not become
        a way to discover which task ids exist, or to link work to a task
        in a project the author cannot see.
        """
        if not task_ids:
            return self.env['project.task']
        return self.env['project.task'].search([('id', 'in', list(task_ids))])
