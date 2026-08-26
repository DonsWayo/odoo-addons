/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS, loadCSS } from "@web/core/assets";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const DIFF2HTML_JS = "/dw_git/static/lib/diff2html/diff2html-ui-slim.min.js";
const DIFF2HTML_CSS = "/dw_git/static/lib/diff2html/diff2html.min.css";

export class GitDiffViewerField extends Component {
    static template = "dw_git.GitDiffViewerField";
    static props = { ...standardFieldProps };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({ empty: !this.props.record.data[this.props.name] });

        onWillStart(async () => {
            await Promise.all([loadJS(DIFF2HTML_JS), loadCSS(DIFF2HTML_CSS)]);
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
        // eslint-disable-next-line no-undef
        this.ui = new Diff2HtmlUI(this.rootRef.el, patch, {
            outputFormat: "side-by-side",
            drawFileList: false,
            matching: "lines",
        });
        this.ui.draw();
        this.ui.highlightCode();
    }
}

registry.category("fields").add("git_diff_viewer", {
    component: GitDiffViewerField,
    supportedTypes: ["text"],
});
