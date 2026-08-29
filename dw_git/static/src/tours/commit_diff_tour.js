/** @odoo-module **/
import { registry } from "@web/core/registry";

/**
 * A commit shows what it changed.
 *
 * The stats panel (Lines Added / Deleted / Files Changed) was rendered on
 * every commit page and never populated, and _get_diff() existed on the
 * model with nothing calling it. So a commit page showed a message and no
 * code, confidently, for the life of the product. Structure alone would
 * not have caught that — the panel was always there. These steps assert
 * the NUMBERS and the DIFF TEXT.
 *
 * No `url` property: the test supplies the record URL.
 */
registry.category("web_tour.tours").add("dw_git_commit_diff", {
    steps: () => [
        {
            trigger: ".o_form_view",
            content: "Commit form is open",
            run: false,
        },
        {
            trigger: ".nav-link:contains('Changes')",
            content: "Open the Changes tab",
            run: "click",
        },
        {
            trigger: ".o_git_diff_viewer .d2h-wrapper",
            content: "diff2html mounted for the commit",
            run: false,
        },
        {
            trigger: ".o_git_diff_viewer .d2h-ins",
            content: "An added line is rendered",
            run: false,
        },
        {
            // the stats that were always zero
            trigger: ".o_form_view",
            content: "The commit reports real numbers, not zeros",
            run: () => {
                const text = document.body.innerText;
                if (/Lines Added\s*0\b/.test(text)) {
                    throw new Error(
                        "commit reports 0 lines added — stats are not populated");
                }
            },
        },
    ],
});
