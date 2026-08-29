/** @odoo-module **/
import { registry } from "@web/core/registry";

/**
 * Reviews and approvals, as a person sees them.
 *
 * No `url` property: the test passes the record URL as startUrl, and a
 * tour that declares one navigates there on start and discards it.
 *
 * The assertions are about VALUES, not about the shape of the table.
 * Asserting that column headers exist would have passed for the whole life
 * of the feature no matter what the numbers said — which is exactly how
 * the diff viewer shipped with no syntax highlighting and how every commit
 * reported zero changes.
 */
registry.category("web_tour.tours").add("dw_git_pr_review", {
    steps: () => [
        {
            trigger: ".o_form_view",
            content: "Pull request form is open",
            run: false,
        },
        {
            trigger: ".nav-link:contains('Reviews')",
            content: "Open the Reviews tab",
            run: "click",
        },
        {
            trigger: "[name='review_ids'] .o_data_row",
            content: "A review is listed",
            run: false,
        },
        {
            // the review's STATE, not merely that a cell exists
            trigger: "[name='review_ids'] .o_data_row",
            content: "The review shows the state it was given",
            run: () => {
                const row = document.querySelector(
                    "[name='review_ids'] .o_data_row");
                const text = (row.innerText || "").toLowerCase();
                if (!text.includes("approve")) {
                    throw new Error(
                        `review row does not show its state: "${row.innerText}"`);
                }
            },
        },
        {
            // the approval count is a computed field; a stale or zero count
            // beside a visible approval is the bug worth catching
            trigger: ".o_field_widget[name='approval_count']",
            content: "The approval count reflects the approval",
            run: () => {
                const el = document.querySelector(
                    ".o_field_widget[name='approval_count']");
                // statinfo renders the VALUE and the LABEL together, and
                // their order is not ours to rely on — parseInt on the raw
                // text would read "Approvals" and yield NaN. Take the first
                // number that appears instead.
                const match = (el.innerText || "").match(/\d+/);
                const count = match ? parseInt(match[0], 10) : NaN;
                if (!(count >= 1)) {
                    throw new Error(
                        `approval_count reads "${el.innerText}" with an ` +
                        `approving review present`);
                }
            },
        },
    ],
});
