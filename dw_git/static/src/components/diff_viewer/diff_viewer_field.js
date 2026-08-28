/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS, loadCSS } from "@web/core/assets";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const DIFF2HTML_JS = "/dw_git/static/lib/diff2html/diff2html-ui-slim.min.js";
const DIFF2HTML_CSS = "/dw_git/static/lib/diff2html/diff2html.min.css";
// The "slim" bundle does NOT carry highlight.js. Its constructor reads
//   this.hljs = null; ... void 0 !== r && (this.hljs = r)
// so hljs arrives as the fourth argument, and without it highlightCode()
// runs and does nothing. Its theme stylesheet is equally required: hljs
// emits <span class="hljs-keyword"> and nothing colours them otherwise.
const HLJS_JS = "/dw_git/static/lib/highlightjs/highlight.min.js";
const HLJS_CSS = "/dw_git/static/lib/highlightjs/github.min.css";

export class GitDiffViewerField extends Component {
    static template = "dw_git.GitDiffViewerField";
    static props = { ...standardFieldProps };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({ empty: !this.props.record.data[this.props.name] });

        onWillStart(async () => {
            // hljs must be loaded before diff2html is constructed with it
            await Promise.all([
                loadJS(HLJS_JS), loadJS(DIFF2HTML_JS),
                loadCSS(HLJS_CSS), loadCSS(DIFF2HTML_CSS),
            ]);
        });
        onMounted(() => this.renderDiff());
        onWillUnmount(() => {
            this.ui = undefined;
        });
    }

    renderDiff() {
        const patch = this.props.record.data[this.props.name];
        if (!patch || !this.rootRef.el) {
            this.state.empty = true;
            return;
        }
        this.state.empty = false;
        // Line-by-line, not side-by-side: an Odoo form dialog is far narrower
        // than a code review page, and side-by-side halves that again — long
        // lines were being clipped, and a pure add/delete left one column
        // showing nothing at all.
        // eslint-disable-next-line no-undef
        const hljs = window.hljs;
        this.ui = new Diff2HtmlUI(this.rootRef.el, patch, {
            outputFormat: "line-by-line",
            drawFileList: false,
            // word-level, so a one-token change reads as a one-token change
            // rather than a whole line replaced
            matching: "words",
            highlight: true,
        }, hljs);
        this.ui.draw();
        this.ui.highlightCode();
    }
}

registry.category("fields").add("git_diff_viewer", {
    component: GitDiffViewerField,
    supportedTypes: ["text"],
});
