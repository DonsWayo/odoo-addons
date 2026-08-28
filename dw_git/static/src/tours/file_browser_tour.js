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
    // Started on a specific repository's FORM by the test, not on the list
    // — see the note in pr_diff_tour.js.
    // No `url` here on purpose. A tour that declares one makes the tour
    // service navigate to it when the tour starts, which threw away the
    // startUrl the test passed — the browser loaded the record, then
    // immediately reloaded the bare action and landed on the LIST, so
    // .o_form_view never appeared. The test supplies the URL.
    steps: () => [
        {
            trigger: ".o_form_view",
            content: "Repository form is open",
            run: false,
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
