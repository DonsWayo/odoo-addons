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
    // The test starts this tour on a specific pull request's FORM, built in
    // setUpClass with a known patch — not on the list. Opening "the first
    // row" would depend on ordering and on whatever else the database holds,
    // and there is no list view on a record URL at all: the tour used to
    // click a row inside the form's own one2many and navigate away from the
    // record it was supposed to be testing.
    // No `url` here on purpose. A tour that declares one makes the tour
    // service navigate to it when the tour starts, which threw away the
    // startUrl the test passed — the browser loaded the record, then
    // immediately reloaded the bare action and landed on the LIST, so
    // .o_form_view never appeared. The test supplies the URL.
    steps: () => [
        {
            trigger: ".o_form_view",
            content: "Pull request form is open",
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
            // The field wrapper Odoo generates inherits
            // `.o_field_widget { display: inline-block }`, which shrinks to
            // its content: a short diff rendered as a narrow column with the
            // rest of the dialog empty beside it. Nothing failed, it just
            // looked broken. Assert the widget actually fills its parent.
            trigger: ".o_field_git_diff_viewer",
            content: "The diff viewer fills the width available to it",
            run: function () {
                const el = document.querySelector(".o_field_git_diff_viewer");
                const parent = el.parentElement;
                const own = el.getBoundingClientRect().width;
                const avail = parent.getBoundingClientRect().width;
                if (own < avail - 2) {
                    throw new Error(
                        `diff viewer collapsed: ${Math.round(own)}px inside ` +
                        `${Math.round(avail)}px — the field wrapper is still ` +
                        `inline-block`);
                }
            },
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
