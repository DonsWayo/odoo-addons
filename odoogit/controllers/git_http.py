# -*- coding: utf-8 -*-
import os
import subprocess
import logging
import hashlib
import base64

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class GitHTTPController(http.Controller):
    """
    Implements Git Smart HTTP Protocol (RFC 3645)
    Endpoints:
    - GET  /git/<owner>/<repo>.git/info/refs?service=git-upload-pack    # fetch/clone
    - POST /git/<owner>/<repo>.git/git-upload-pack                       # fetch/clone
    - POST /git/<owner>/<repo>.git/git-receive-pack                      # push
    """

    def _get_repo_path(self, repository):
        """Get filesystem path for repository"""
        return repository._get_repo_path()

    def _auth_challenge_or_404(self, owner, repo):
        """Git clients only send credentials after a 401 + WWW-Authenticate.
        Return a 401 challenge when the repo exists but access failed,
        a plain 404 when it does not exist (do not leak existence)."""
        exists = request.env['git.repository'].sudo().search_count([
            ('name', '=', repo),
            ('owner_id.login', '=', owner),
        ])
        if exists:
            return request.make_response(
                b'Authentication required\n',
                status=401,
                headers=[('WWW-Authenticate', 'Basic realm="OdooGit"'),
                         ('Content-Type', 'text/plain')],
            )
        return request.not_found()

    def _get_repo(self, owner, repo, operation='read'):
        """Find repository and check access.

        Returns (repository, user) — user is the authenticated identity
        (PAT owner, deploy-key context, or session user) so downstream
        checks (branch protection, webhooks) run as the right user.
        Returns (None, None) when access is denied."""
        repository = request.env['git.repository'].sudo().search([
            ('name', '=', repo),
            ('owner_id.login', '=', owner),
        ], limit=1)

        if not repository:
            return None, None

        # Check access via Authorization header (PAT or Deploy Key)
        auth_header = request.httprequest.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                pat = request.env['git.personal_access_token'].sudo().find_by_token(token)
                if pat and (not pat.repository_ids or repository in pat.repository_ids):
                    if operation == 'read' or pat.scopes == 'write':
                        return repository, pat.user_id
            elif auth_header.startswith('Basic '):
                try:
                    credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
                    if ':' in credentials:
                        _, password = credentials.split(':', 1)
                        pat = request.env['git.personal_access_token'].sudo().find_by_token(password)
                        if pat and (not pat.repository_ids or repository in pat.repository_ids):
                            if operation == 'read' or pat.scopes == 'write':
                                return repository, pat.user_id
                        deploy_key = request.env['git.deploy_key'].sudo().find_by_token(password)
                        if deploy_key and deploy_key.repository_id == repository:
                            if operation == 'read' or deploy_key.can_push:
                                # deploy keys are not user-bound; act as repo owner
                                return repository, repository.owner_id
                except Exception:
                    pass

        # Check session user access
        if repository._check_repo_access(request.env.user, operation):
            return repository, request.env.user

        return None, None

    def _run_git_command(self, repo_path, command, input_data=None, env=None):
        """Run git command with proper environment"""
        cmd_env = os.environ.copy()
        cmd_env.update({
            'GIT_PROJECT_ROOT': os.path.dirname(repo_path),
            'HOME': '/tmp',
        })
        if env:
            cmd_env.update(env)
        
        # Ensure git-daemon-export-ok exists (never crash the route on FS issues)
        try:
            export_ok = os.path.join(repo_path, 'git-daemon-export-ok')
            if not os.path.exists(export_ok):
                with open(export_ok, 'w') as f:
                    f.write('')
        except OSError as e:
            _logger.error('Cannot write git-daemon-export-ok in %s: %s', repo_path, e)
        
        full_cmd = ['git', '-c', 'http.receivepack=true'] + command
        _logger.debug(f"Running git command: {full_cmd}")
        
        result = subprocess.run(
            full_cmd,
            cwd=repo_path,
            input=input_data,
            capture_output=True,
            env=cmd_env
        )
        return result

    @http.route('/git/<string:owner>/<string:repo>.git/info/refs', type='http', auth='public', methods=['GET'], csrf=False)
    def info_refs(self, owner, repo, **kwargs):
        """Advertise refs - entry point for clone/fetch"""
        service = kwargs.get('service', 'git-upload-pack')

        repository, auth_user = self._get_repo(owner, repo, 'read')
        if not repository:
            return self._auth_challenge_or_404(owner, repo)

        repo_path = self._get_repo_path(repository)
        
        # Use git-http-backend for proper protocol handling
        result = self._run_git_command(
            repo_path,
            ['http-backend'],
            input_data=None,
            env={
                'PATH_INFO': f'/{repository.name}.git/info/refs',
                'QUERY_STRING': f'service={service}',
                'REQUEST_METHOD': 'GET',
                'CONTENT_TYPE': '',
                'REMOTE_USER': auth_user.login or 'anonymous',
            }
        )

        if result.returncode != 0:
            _logger.error(f"info/refs failed: {result.stderr.decode()}")
            return request.not_found()

        # Parse CGI response
        headers, body = self._parse_cgi_response(result.stdout)
        
        response_headers = [
            ('Content-Type', headers.get('Content-Type', f'application/x-{service}-advertisement')),
            ('Cache-Control', 'no-cache'),
            ('Expires', 'Fri, 01 Jan 1980 00:00:00 GMT'),
        ]
        
        return request.make_response(body, headers=response_headers)

    @http.route('/git/<string:owner>/<string:repo>.git/git-upload-pack', type='http', auth='public', methods=['POST'], csrf=False)
    def upload_pack(self, owner, repo, **kwargs):
        """Handle git fetch/clone (read operation)"""
        repository, auth_user = self._get_repo(owner, repo, 'read')
        if not repository:
            return self._auth_challenge_or_404(owner, repo)

        repo_path = self._get_repo_path(repository)
        data = request.httprequest.get_data()

        result = self._run_git_command(
            repo_path,
            ['http-backend'],
            input_data=data,
            env={
                'PATH_INFO': f'/{repository.name}.git/git-upload-pack',
                'QUERY_STRING': '',
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': 'application/x-git-upload-pack-request',
                'REMOTE_USER': auth_user.login or 'anonymous',
            }
        )

        if result.returncode != 0:
            _logger.error(f"upload-pack failed: {result.stderr.decode()}")
            return request.not_found()

        headers, body = self._parse_cgi_response(result.stdout)
        
        response_headers = [
            ('Content-Type', headers.get('Content-Type', 'application/x-git-upload-pack-result')),
            ('Cache-Control', 'no-cache'),
        ]
        
        return request.make_response(body, headers=response_headers)

    @http.route('/git/<string:owner>/<string:repo>.git/git-receive-pack', type='http', auth='public', methods=['POST'], csrf=False)
    def receive_pack(self, owner, repo, **kwargs):
        """Handle git push (write operation)"""
        repository, auth_user = self._get_repo(owner, repo, 'write')
        if not repository:
            return self._auth_challenge_or_404(owner, repo)

        # Check write access / branch protection before processing
        if not self._check_branch_protection(repository, auth_user):
            return request.make_response(
                b'Access denied: push not permitted on this repository\n',
                status=403,
                headers=[('Content-Type', 'text/plain')],
            )

        repo_path = self._get_repo_path(repository)
        data = request.httprequest.get_data()
        result = self._run_git_command(
            repo_path,
            ['http-backend'],
            input_data=data,
            env={
                'PATH_INFO': f'/{repository.name}.git/git-receive-pack',
                'QUERY_STRING': '',
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': 'application/x-git-receive-pack-request',
                'REMOTE_USER': auth_user.login or 'anonymous',
            }
        )

        if result.returncode != 0:
            _logger.error(f"receive-pack failed: {result.stderr.decode()}")

        headers, body = self._parse_cgi_response(result.stdout)
        
        response_headers = [
            ('Content-Type', headers.get('Content-Type', 'application/x-git-receive-pack-result')),
            ('Cache-Control', 'no-cache'),
        ]
        
        # Trigger post-receive webhooks
        self._trigger_post_receive_hooks(repository, auth_user)
        
        return request.make_response(body, headers=response_headers)

    def _parse_cgi_response(self, output):
        """Parse CGI response into headers and body"""
        if not output:
            return {}, b''
        
        # Find end of headers
        header_end = output.find(b'\r\n\r\n')
        if header_end == -1:
            header_end = output.find(b'\n\n')
            if header_end == -1:
                return {}, output
        
        header_data = output[:header_end]
        body = output[header_end + 4:]  # skip \r\n\r\n
        
        headers = {}
        for line in header_data.split(b'\r\n'):
            if b':' in line:
                key, value = line.split(b':', 1)
                headers[key.decode().strip()] = value.decode().strip()
        
        return headers, body

    def _check_branch_protection(self, repository, user):
        """Check if push is allowed based on branch protection rules"""
        # The actual protection is enforced via git pre-receive hook
        # Here we just do a basic check
        return repository._check_repo_access(user, 'write')

    def _trigger_post_receive_hooks(self, repository, user):
        """Trigger webhooks and update branch refs after push"""
        try:
            # Sync branches + commits from the bare repo into Odoo
            repository.sudo()._sync_from_git()

            # Trigger webhooks
            for webhook in repository.webhook_ids.filtered(lambda w: w.is_active and w.event_push):
                webhook._process_event('push', {
                    'repository': {
                        'id': repository.id,
                        'name': repository.name,
                        'owner': repository.owner_id.login,
                    },
                    'pusher': {
                        'name': user.name,
                        'email': user.email,
                    },
                    'ref': 'refs/heads/main',  # Simplified
                })
        except Exception as e:
            _logger.error(f"Post-receive hook failed: {e}")