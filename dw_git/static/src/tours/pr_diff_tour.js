/** @odoo-module **/
import { registry } from "@web/core/registry";

/**
 * The diff viewer, end to end through the real client.
 *
 * Every bug this covers rendered *something* — an empty pane, a wall of
 * unreadable text, rows three lines tall — while the suite stayed green,
 * because nothing ever opened the dialog. So the assertions here are about
 * what a person can actually read: the file name, a real added line from
 * the patch, and the coloured markup diff2html produces.
 */
registry.category("web_tour.tours").add("dw_git_pr_diff", {
    url: "/odoo/action-dw_git.action_git_pull_request",
    steps: () => [
        {
            trigger: ".o_list_view .o_data_row",
            content: "Open the first pull request",
            run: "click",
        },
        {
            trigger: ".o_form_view",
            content: "Pull request form opened",
            run: false,
        },
        {
            trigger: ".nav-link:contains('Changes')",
            content: "Open the Changes tab",
            run: "click",
        },
        {
            trigger: ".o_field_one2many .o_data_row",
            content: "A changed file is listed",
            run: "click",
        },
        {
            trigger: ".modal .o_form_view, .o_form_view:has(.o_git_diff_viewer)",
            content: "The changed-file record opened",
            run: false,
        },
        {
            // the widget mounted at all — this is what a missing asset or a
            // JS error would break, silently, in the old code
            trigger: ".o_git_diff_viewer .d2h-wrapper",
            content: "diff2html mounted and produced markup",
            run: false,
        },
        {
            // and it rendered a real hunk, not an empty shell. d2h-ins is the
            // class diff2html gives an added line.
            trigger: ".o_git_diff_viewer .d2h-ins",
            content: "An added line is rendered, coloured",
            run: false,
        },
        {
            trigger: ".o_git_diff_viewer .d2h-code-line-ctn",
            content: "Diff line content is present",
            run: false,
        },
        {
            // Syntax highlighting is claimed in the README, the manifest and
            // the store listing, and was broken for the whole life of the
            // feature: the diff2html "slim" bundle does not carry
            // highlight.js, so highlightCode() ran and did nothing. Nothing
            // failed — the code was simply black. Assert a real hljs token.
            trigger: ".o_git_diff_viewer .hljs-keyword",
            content: "highlight.js coloured a keyword in the diff",
            run: false,
        },
        {
            trigger: ".o_git_diff_viewer .hljs-string",
            content: "...and a string literal",
            run: false,
        },
        {
            trigger: ".nav-link:contains('Raw Patch')",
            content: "Switch to the raw patch",
            run: "click",
        },
        {
            trigger: "textarea:value(diff --git)",
            content: "The raw patch is a real unified diff",
            run: false,
        },
    ],
});
