/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState, useRef, onMounted, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS, loadCSS } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";

const HLJS_JS = "/dw_git/static/lib/highlightjs/highlight.min.js";
const HLJS_CSS = "/dw_git/static/lib/highlightjs/github.min.css";

export class GitFileBrowser extends Component {
    static template = "dw_git.GitFileBrowser";
    static props = { ...(Component.props || {}), action: { type: Object, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.codeRef = useRef("code");
        this.repoId = this.props.action?.context?.active_id;

        this.state = useState({
            repoName: "",
            branches: [],
            ref: "",
            path: "",
            entries: [],
            selectedFile: null,
            fileContent: "",
            fileBinary: false,
            fileTooLarge: false,
            loading: true,
        });

        onWillStart(async () => {
            await Promise.all([loadJS(HLJS_JS), loadCSS(HLJS_CSS)]);
            await this.loadRepo();
            await this.loadTree("");
        });

        onMounted(() => this.highlight());
        onWillUpdateProps(() => this.highlight());
    }

    highlight() {
        // eslint-disable-next-line no-undef
        if (this.codeRef.el && typeof hljs !== "undefined") {
            // eslint-disable-next-line no-undef
            hljs.highlightElement(this.codeRef.el);
        }
    }

    async loadRepo() {
        const [repo] = await this.orm.read("git.repository", [this.repoId], ["name", "default_branch"]);
        const branches = await this.orm.searchRead(
            "git.branch",
            [["repository_id", "=", this.repoId]],
            ["name"],
            { limit: 200 }
        );
        this.state.repoName = repo.name;
        this.state.ref = repo.default_branch;
        this.state.branches = branches.map((b) => b.name);
    }

    async loadTree(path) {
        this.state.loading = true;
        this.state.selectedFile = null;
        const data = await rpc(`/api/git/repositories/${this.repoId}/tree`, {
            ref: this.state.ref,
            path,
        });
        this.state.path = data.path;
        this.state.entries = data.tree.sort((a, b) => {
            if (a.type !== b.type) {
                return a.type === "tree" ? -1 : 1;
            }
            return a.name.localeCompare(b.name);
        });
        this.state.loading = false;
    }

    async openEntry(entry) {
        if (entry.type === "tree") {
            await this.loadTree(entry.path);
            return;
        }
        this.state.loading = true;
        const data = await rpc(`/api/git/repositories/${this.repoId}/blob`, {
            ref: this.state.ref,
            path: entry.path,
        });
        this.state.selectedFile = entry.path;
        this.state.fileBinary = data.binary;
        this.state.fileTooLarge = !!data.too_large;
        this.state.fileContent = data.content;
        this.state.loading = false;
        requestAnimationFrame(() => this.highlight());
    }

    get breadcrumbs() {
        if (!this.state.path) {
            return [];
        }
        const parts = this.state.path.split("/");
        return parts.map((part, i) => ({
            name: part,
            path: parts.slice(0, i + 1).join("/"),
        }));
    }

    async onBranchChange(ev) {
        this.state.ref = ev.target.value;
        await this.loadTree(this.state.path);
    }

    async goToBreadcrumb(path) {
        await this.loadTree(path);
    }
}

registry.category("actions").add("dw_git.file_browser", GitFileBrowser);
