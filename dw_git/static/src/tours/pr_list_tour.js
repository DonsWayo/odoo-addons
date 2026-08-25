/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("dw_git_pr_list", {
    url: "/odoo/action-dw_git.action_git_pull_request",
    steps: () => [
        { trigger: ".o_list_view, .o_kanban_view", content: "PR view rendered", run: false },
        { trigger: "body", content: "E2E PR present", run: () => {
            if (!document.body.innerText.includes("E2E PR")) throw new Error("missing PR");
        }},
    ],
});
