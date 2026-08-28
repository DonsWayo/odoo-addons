/** @odoo-module **/
import { registry } from "@web/core/registry";

/**
 * The read-only file browser, end to end.
 *
 * Covers the parts that can fail quietly: the client action mounting at
 * all, the tree loading from the blob/tree routes, and highlight.js
 * actually colouring the file rather than dumping plain text.
 */
registry.category("web_tour.tours").add("dw_git_file_browser", {
    url: "/odoo/action-dw_git.action_git_repository",
    steps: () => [
        {
            trigger: ".o_list_view .o_data_row",
            content: "Open the first repository",
            run: "click",
        },
        {
            trigger: "button:contains('Browse Files')",
            content: "Open the file browser",
            run: "click",
        },
        {
            trigger: ".o_git_file_browser",
            content: "The client action mounted",
            run: false,
        },
        {
            trigger: ".o_git_file_browser select option",
            content: "The branch selector is populated",
            run: false,
        },
        {
            trigger: ".o_git_file_tree .o_git_tree_entry",
            content: "The tree loaded entries from the repository",
            run: "click",
        },
        {
            trigger: ".o_git_file_content pre code",
            content: "File content is rendered",
            run: false,
        },
        {
            // highlight.js adds hljs-* spans; without them the file is
            // plain text and the library never ran
            trigger: ".o_git_file_content code .hljs-keyword, .o_git_file_content code .hljs-string, .o_git_file_content code .hljs-title",
            content: "highlight.js coloured the source",
            run: false,
        },
    ],
});
