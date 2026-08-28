/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS, loadCSS } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";

const HLJS_JS = "/dw_git/static/lib/highlightjs/highlight.min.js";
const HLJS_CSS = "/dw_git/static/lib/highlightjs/github.min.css";

//: Filename extension -> highlight.js grammar. Auto-detection guesses from
//: content alone and is unreliable on short files: a 3-line __init__.py was
//: routinely detected as something other than Python. We know the filename,
//: so use it.
const EXT_LANGUAGE = {
    py: "python", pyi: "python", js: "javascript", mjs: "javascript",
    ts: "typescript", xml: "xml", html: "xml", htm: "xml", svg: "xml",
    css: "css", scss: "scss", less: "less", json: "json", md: "markdown",
    yml: "yaml", yaml: "yaml", toml: "ini", ini: "ini", cfg: "ini",
    sh: "bash", bash: "bash", zsh: "bash", sql: "sql", rb: "ruby",
    go: "go", rs: "rust", java: "java", php: "php", c: "c", h: "c",
    cpp: "cpp", hpp: "cpp", cs: "csharp", kt: "kotlin", swift: "swift",
    dockerfile: "dockerfile", makefile: "makefile", po: "properties",
};

export class GitFileBrowser extends Component {
    static template = "dw_git.GitFileBrowser";
    // Odoo hands every client action more props than just `action`:
    // actionId, updateActionState and className at least. Declaring only
    // `action` made Owl throw "Invalid props for component
    // 'GitFileBrowser': unknown key 'actionId'..." — but only in dev and
    // test mode, because Owl skips prop validation in production. So the
    // file browser raised on every mount under a tour while appearing to
    // work in normal use, and no tour ever ran to report it.
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.repoId = this.props.action?.context?.active_id;

        this.state = useState({
            repoName: "",
            branches: [],
            ref: "",
            path: "",
            entries: [],
            selectedFile: null,
            fileContent: "",
            fileHtml: "",
            fileBinary: false,
            fileTooLarge: false,
            //: separate flags. A single `loading` meant that clicking a
            //: FILE blanked the whole tree pane to "Loading…" and rebuilt
            //: it, so the directory listing flashed away on every click.
            treeLoading: true,
            fileLoading: false,
            treeError: "",
            fileError: "",
        });

        onWillStart(async () => {
            await Promise.all([loadJS(HLJS_JS), loadCSS(HLJS_CSS)]);
            await this.loadRepo();
            await this.loadTree("");
        });

    }

    /**
     * Produce highlighted HTML for Owl to render, rather than letting
     * highlight.js loose on the live DOM.
     *
     * `hljs.highlightElement(el)` REPLACES the element's children with its
     * own markup, which destroys the text node Owl created for `t-esc`.
     * Owl keeps a reference to that now-detached node, so every later file
     * was written into an orphan and never appeared: the code pane stayed
     * frozen on the first file opened while the tree selection moved on.
     * Selecting AGENTS.md showed the Dockerfile.
     *
     * Computing the markup here and rendering it with `t-out` keeps Owl the
     * only writer of that subtree. hljs escapes the source it is given, so
     * the result is safe to inject.
     */
    highlightToHtml(code, path) {
        const escaped = (code || "")
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        // eslint-disable-next-line no-undef
        if (typeof hljs === "undefined") {
            return escaped;
        }
        const name = (path || "").split("/").pop();
        const ext = name.includes(".")
            ? name.split(".").pop().toLowerCase()
            : name.toLowerCase();
        const lang = EXT_LANGUAGE[ext];
        try {
            // eslint-disable-next-line no-undef
            if (lang && hljs.getLanguage(lang)) {
                // eslint-disable-next-line no-undef
                return hljs.highlight(code, {
                    language: lang, ignoreIllegals: true }).value;
            }
            // eslint-disable-next-line no-undef
            return hljs.highlightAuto(code).value;
        } catch {
            return escaped;      // never let colouring break the viewer
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
        this.state.treeLoading = true;
        this.state.selectedFile = null;
        this.state.treeError = "";
        try {
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
        } catch {
            this.state.treeError = "Could not load this directory.";
        } finally {
            this.state.treeLoading = false;
        }
    }

    async openEntry(entry) {
        if (entry.type === "tree") {
            await this.loadTree(entry.path);
            return;
        }
        if (entry.type !== "blob") {
            // submodule / gitlink entries have no content to read here
            return;
        }
        this.state.fileLoading = true;
        this.state.fileError = "";
        // Select immediately rather than after the round trip, so the row
        // highlights the instant it is clicked instead of staying blank
        // until the content arrives.
        this.state.selectedFile = entry.path;
        try {
            const data = await rpc(`/api/git/repositories/${this.repoId}/blob`, {
                ref: this.state.ref,
                path: entry.path,
            });
            this.state.fileBinary = data.binary;
            this.state.fileTooLarge = !!data.too_large;
            this.state.fileContent = data.content;
            this.state.fileHtml = this.highlightToHtml(
                data.content, entry.path);
        } catch {
            this.state.fileError = "Could not load this file.";
        } finally {
            this.state.fileLoading = false;
        }
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
